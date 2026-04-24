import streamlit as st
import pandas as pd
import psycopg2
import datetime

# --- ページの基本設定 ---
st.set_page_config(page_title="Sayo Brewery 🍺", page_icon="🌾", layout="wide", initial_sidebar_state="expanded")

# --- 接続設定 ---
DB_URL = "postgresql://postgres.qoghpcgjweqyczbbcttj:19960519Tatsuki@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS materials (id SERIAL PRIMARY KEY, name TEXT, unit TEXT, memo TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS accounts (id SERIAL PRIMARY KEY, code TEXT, name TEXT, type TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS journal_entries (id SERIAL PRIMARY KEY, date DATE, description TEXT, debit_account TEXT, credit_account TEXT, amount INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS loans (id SERIAL PRIMARY KEY, lender TEXT, principal BIGINT, interest_rate REAL)')
    cur.execute('CREATE TABLE IF NOT EXISTS products (id SERIAL PRIMARY KEY, name TEXT, volume_ml INTEGER, price INTEGER, stock INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS tax_records (id SERIAL PRIMARY KEY, date DATE, product_name TEXT, quantity INTEGER, total_liters REAL, tax_amount INTEGER)')

    # 必須勘定科目のセットアップ
    required_accounts = [
        ('120', '仕掛品', '資産'), ('121', '製品', '資産'),
        ('411', '売上高', '収益'), ('210', '未払酒税', '負債'), ('511', '租税公課', '費用'),
        ('100', '現預金', '資産'), ('150', '原材料', '資産')
    ]
    for code, name, acc_type in required_accounts:
        cur.execute("SELECT * FROM accounts WHERE name = %s", (name,))
        if not cur.fetchone():
            cur.execute("INSERT INTO accounts (code, name, type) VALUES (%s, %s, %s)", (code, name, acc_type))

    conn.commit()
    cur.close()
    conn.close()

init_db()

def load_data(table_name):
    conn = get_connection()
    df = pd.read_sql(f"SELECT * FROM {table_name} ORDER BY id DESC", conn)
    conn.close()
    return df

def delete_record(table_name, record_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table_name} WHERE id = %s", (record_id,))
    conn.commit()
    cur.close()
    conn.close()

# ==========================================
# サイドバー
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3075/3075908.png", width=50)
    st.title("Sayo Brewery")
    st.caption("v7.0 Management Edition")
    st.divider()
    menu = st.radio(
        "📂 メニュー",
        ("🏠 ホーム", "🏪 直売所レジ", "📈 利益分析", "🧪 製造", "📦 在庫", "📜 酒税帳簿", "📝 経理・マスタ", "🔧 システム管理"),
        label_visibility="collapsed"
    )
    st.divider()
    st.success("🟢 クラウド同期中")

# ==========================================
# 各画面のロジック
# ==========================================

if menu == "🏠 ホーム":
    st.header("🏠 経営ダッシュボード")
    df_j = load_data("journal_entries")
    col1, col2, col3, col4 = st.columns(4)
    if not df_j.empty:
        cash = df_j[df_j['debit_account'] == '現預金']['amount'].sum() - df_j[df_j['credit_account'] == '現預金']['amount'].sum()
        sales = df_j[df_j['credit_account'] == '売上高']['amount'].sum()
        stock_val = df_j[df_j['debit_account'] == '製品']['amount'].sum() - df_j[df_j['credit_account'] == '製品']['amount'].sum()
        tax = df_j[df_j['credit_account'] == '未払酒税']['amount'].sum()
    else: cash, sales, stock_val, tax = 0, 0, 0, 0
    col1.metric("💰 現預金残高", f"¥ {cash:,}")
    col2.metric("📈 累計売上高", f"¥ {sales:,}")
    col3.metric("🍾 在庫資産額", f"¥ {stock_val:,}")
    col4.metric("⚠️ 納税予定(酒税)", f"¥ {tax:,}")
    st.subheader("最近の動き")
    st.dataframe(df_j.head(10), use_container_width=True, hide_index=True)

elif menu == "🏪 直売所レジ":
    st.header("🏪 かんたんPOSレジ")
    df_p = load_data("products")
    if df_p.empty: st.warning("製品を登録してください")
    else:
        with st.form("pos"):
            options = [f"{r['name']} (在庫:{r['stock']}) ¥{r['price']}" for _,r in df_p.iterrows()]
            sel = st.selectbox("商品選択", options)
            num = st.number_input("個数", min_value=1, value=1)
            name = sel.split(" (")[0]; price = int(sel.split("¥")[1]); total = price * num
            st.metric("合計金額", f"¥ {total:,}")
            if st.form_submit_button("会計完了", type="primary"):
                conn = get_connection(); cur = conn.cursor()
                cur.execute("UPDATE products SET stock = stock - %s WHERE name = %s", (num, name))
                cur.execute("SELECT volume_ml FROM products WHERE name = %s", (name,))
                ml = cur.fetchone()[0]; l = (ml * num) / 1000.0; tax = int(l * 140); today = datetime.date.today()
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (today, f"売上:{name}x{num}", '現預金', '売上高', total))
                cur.execute("INSERT INTO tax_records (date, product_name, quantity, total_liters, tax_amount) VALUES (%s,%s,%s,%s,%s)", (today, name, num, l, tax))
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (today, f"酒税計上:{l}L", '租税公課', '未払酒税', tax))
                conn.commit(); cur.close(); conn.close()
                st.balloons(); st.toast("売上を記録しました")

elif menu == "📈 利益分析":
    st.header("📈 限界利益シミュレーター")
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            p = st.number_input("販売価格(円)", value=2000)
            ml = st.number_input("容器容量(ml)", value=330) # ★柔軟に変更可能に
            m_c = st.number_input("原材料費/本(円)", value=300)
            p_c = st.number_input("資材費/本(円)", value=150)
            qty = st.number_input("予定本数", value=500)
            tax_b = int((ml / 1000) * 140)
            profit = p - (m_c + p_c + tax_b)
        with c2:
            st.metric("1本当たりの利益", f"¥ {profit:,}")
            st.metric("バッチ総利益予測", f"¥ {profit * qty:,}")
            st.bar_chart(pd.DataFrame({"額": [p*qty, (m_c+p_c+tax_b)*qty, profit*qty]}, index=["売上", "費用", "利益"]))

elif menu == "🧪 製造":
    st.header("🧪 仕込み記録")
    m_df = load_data("materials")
    with st.form("brew"):
        m_name = st.selectbox("原料", m_df['name'].tolist() if not m_df.empty else ["なし"])
        amt = st.number_input("使用量", value=10.0); cost = st.number_input("単価", value=800)
        total = int(amt * cost)
        if st.form_submit_button("仕込み開始"):
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (datetime.date.today(), f"仕込:{m_name}", '仕掛品', '原材料', total))
            conn.commit(); cur.close(); conn.close()
            st.toast("記録しました")

elif menu == "📦 在庫":
    st.header("📦 在庫管理")
    p_df = load_data("products")
    st.dataframe(p_df, use_container_width=True, hide_index=True)
    with st.expander("瓶詰め（仕掛品 → 製品）を記録"):
        with st.form("bottle"):
            target = st.selectbox("製品名", p_df['name'].tolist() if not p_df.empty else ["なし"])
            num = st.number_input("本数", value=100); cost = st.number_input("振替原価", value=50000)
            if st.form_submit_button("瓶詰め完了"):
                conn = get_connection(); cur = conn.cursor()
                cur.execute("UPDATE products SET stock = stock + %s WHERE name = %s", (num, target))
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (datetime.date.today(), f"瓶詰:{target}", '製品', '仕掛品', cost))
                conn.commit(); cur.close(); conn.close()
                st.success("在庫を更新しました")

elif menu == "📜 酒税帳簿":
    st.header("📜 酒税法定帳簿")
    t_df = load_data("tax_records")
    st.metric("今月の総出荷量", f"{t_df['total_liters'].sum() if not t_df.empty else 0} L")
    st.dataframe(t_df, use_container_width=True, hide_index=True)

elif menu == "📝 経理・マスタ":
    st.header("📝 経理・マスタ管理")
    t1, t2, t3, t4 = st.tabs(["💰 仕訳", "🌾 原材料", "🍾 製品", "🗑️ データ整理"])
    
    with t1:
        acc = load_data("accounts")
        with st.form("j"):
            c1,c2,c3 = st.columns(3)
            d=c1.date_input("日"); db=c2.selectbox("借", acc['name'].tolist()); cr=c3.selectbox("貸", acc['name'].tolist())
            a=st.number_input("金額"); desc=st.text_input("摘要")
            if st.form_submit_button("登録"):
                conn=get_connection(); cur=conn.cursor(); cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (d,desc,db,cr,a)); conn.commit(); cur.close(); conn.close()
        st.dataframe(load_data("journal_entries"), use_container_width=True)

    with t2:
        with st.form("m"):
            n=st.text_input("原料名"); u=st.text_input("単位(kg等)"); memo=st.text_input("メモ")
            if st.form_submit_button("登録"):
                conn=get_connection(); cur=conn.cursor(); cur.execute("INSERT INTO materials (name, unit, memo) VALUES (%s,%s,%s)", (n,u,memo)); conn.commit(); cur.close(); conn.close()
        st.dataframe(load_data("materials"), use_container_width=True)

    with t3:
        with st.form("p"):
            n=st.text_input("製品名"); v=st.number_input("容量(ml)", value=330); p=st.number_input("売価", value=800)
            if st.form_submit_button("登録"):
                conn=get_connection(); cur=conn.cursor(); cur.execute("INSERT INTO products (name, volume_ml, price, stock) VALUES (%s,%s,%s,0)", (n,v,p)); conn.commit(); cur.close(); conn.close()
        st.dataframe(load_data("products"), use_container_width=True)

    with t4:
        st.subheader("個別にデータを削除する")
        st.write("間違えて登録したIDを選択して削除してください。")
        
        target_table = st.selectbox("削除するデータの種類", ["仕訳 (journal_entries)", "出荷帳簿 (tax_records)", "原材料マスタ (materials)", "製品マスタ (products)"])
        table_map = {"仕訳 (journal_entries)": "journal_entries", "出荷帳簿 (tax_records)": "tax_records", "原材料マスタ (materials)": "materials", "製品マスタ (products)": "products"}
        
        df_del = load_data(table_map[target_table])
        if not df_del.empty:
            del_id = st.selectbox("削除するIDを選択", df_del['id'].tolist())
            if st.button("選択したデータを削除する", type="secondary"):
                delete_record(table_map[target_table], del_id)
                st.toast("削除しました。画面を更新してください。")
        else: st.info("データがありません")

elif menu == "🔧 システム管理":
    st.header("🔧 システムメンテナンス")
    st.warning("【危険エリア】本番開始前のテストデータ一掃用です。")
    
    confirm = st.checkbox("すべての取引データ（仕訳・出荷記録）を消去することに同意します")
    if st.button("取引データのみリセット", disabled=not confirm):
        conn = get_connection(); cur = conn.cursor()
        cur.execute("TRUNCATE TABLE journal_entries, tax_records RESTART IDENTITY")
        conn.commit(); cur.close(); conn.close()
        st.success("取引データをリセットしました！")

    st.divider()
    confirm_all = st.checkbox("マスタを含むすべてのデータ（原材料・製品も含む）を完全に消去します")
    if st.button("データベースを完全初期化", disabled=not confirm_all):
        conn = get_connection(); cur = conn.cursor()
        cur.execute("TRUNCATE TABLE journal_entries, tax_records, materials, products, loans RESTART IDENTITY")
        conn.commit(); cur.close(); conn.close()
        st.success("すべてのデータを消去しました。")
