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
    conn = get_connection(); cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS materials (id SERIAL PRIMARY KEY, name TEXT, unit TEXT, memo TEXT, stock REAL DEFAULT 0, unit_price INTEGER DEFAULT 0)')
    cur.execute('CREATE TABLE IF NOT EXISTS accounts (id SERIAL PRIMARY KEY, code TEXT, name TEXT, type TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS journal_entries (id SERIAL PRIMARY KEY, date DATE, description TEXT, debit_account TEXT, credit_account TEXT, amount INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS loans (id SERIAL PRIMARY KEY, lender TEXT, principal BIGINT, interest_rate REAL)')
    cur.execute('CREATE TABLE IF NOT EXISTS products (id SERIAL PRIMARY KEY, name TEXT, volume_ml INTEGER, price INTEGER, stock INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS tax_records (id SERIAL PRIMARY KEY, date DATE, product_name TEXT, quantity INTEGER, total_liters REAL, tax_amount INTEGER)')

    required_accounts = [
        ('120', '仕掛品', '資産'), ('121', '製品', '資産'),
        ('411', '売上高', '収益'), ('210', '未払酒税', '負債'), ('511', '租税公課', '費用'),
        ('100', '現預金', '資産'), ('150', '原材料', '資産')
    ]
    for code, name, acc_type in required_accounts:
        cur.execute("SELECT * FROM accounts WHERE name = %s", (name,))
        if not cur.fetchone():
            cur.execute("INSERT INTO accounts (code, name, type) VALUES (%s, %s, %s)", (code, name, acc_type))
    conn.commit(); cur.close(); conn.close()

init_db()

def load_data(table_name):
    conn = get_connection(); df = pd.read_sql(f"SELECT * FROM {table_name} ORDER BY id DESC", conn); conn.close(); return df

def delete_record(table_name, record_id):
    conn = get_connection(); cur = conn.cursor(); cur.execute(f"DELETE FROM {table_name} WHERE id = %s", (record_id,)); conn.commit(); cur.close(); conn.close()

# ==========================================
# サイドバー
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3075/3075908.png", width=50)
    st.title("Sayo Brewery")
    st.caption("v10.0 Unified POS (Full Edition)")
    st.divider()
    menu = st.radio("📂 メニュー", ("🏠 ホーム", "🏪 直売所レジ", "🧪 仕込み記録", "📦 在庫管理", "📈 利益分析", "📜 酒税帳簿", "📝 経理・マスタ", "🔧 システム管理"), label_visibility="collapsed")
    st.divider()
    st.success("🟢 クラウド同期中")

# ==========================================
# メインロジック
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
    if df_p.empty: st.warning("製品マスタから商品を登録してください")
    else:
        with st.container(border=True):
            with st.form("pos"):
                sel_p = st.selectbox("商品を選択", df_p['name'].tolist())
                row = df_p[df_p['name'] == sel_p].iloc[0]
                
                st.write(f"現在の在庫: **{row['stock']}本** | 定価: ¥{row['price']:,}")
                price_type = st.radio("販売区分", ["定価 (そのまま)", "創業特価 (1,980円)", "卸売 (7掛)", "カスタム自由入力"], horizontal=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    num = st.number_input("販売数量", min_value=1, value=1)
                with col2:
                    if price_type == "定価 (そのまま)": unit_p = row['price']
                    elif price_type == "創業特価 (1,980円)": unit_p = 1980
                    elif price_type == "卸売 (7掛)": unit_p = int(row['price'] * 0.7)
                    else: unit_p = st.number_input("自由単価入力(円)", value=row['price'])
                    
                    total = unit_p * num
                    st.metric("お会計合計", f"¥ {total:,}")

                if st.form_submit_button("💰 会計完了（売上計上）", type="primary"):
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute("UPDATE products SET stock = stock - %s WHERE name = %s", (num, sel_p))
                    l = (row['volume_ml'] * num) / 1000.0; tax = int(l * 140); today = datetime.date.today()
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (today, f"売上({price_type}):{sel_p}x{num}", '現預金', '売上高', total))
                    cur.execute("INSERT INTO tax_records (date, product_name, quantity, total_liters, tax_amount) VALUES (%s,%s,%s,%s,%s)", (today, sel_p, num, l, tax))
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (today, f"酒税計上:{l}L", '租税公課', '未払酒税', tax))
                    conn.commit(); cur.close(); conn.close()
                    st.balloons(); st.toast("売上と酒税を記録しました！")

elif menu == "🧪 仕込み記録":
    st.header("🧪 配合ベース仕込み記録")
    m_df = load_data("materials")
    if m_df.empty:
        st.warning("先に原材料マスタから在庫と単価を登録してください。")
    else:
        with st.form("brew"):
            batch_name = st.text_input("バッチ名/管理番号", value=f"BATCH-{datetime.date.today().strftime('%m%d')}")
            col1, col2, col3 = st.columns(3)
            with col1: k_name = st.selectbox("掛米", m_df['name'].tolist()); k_qty = st.number_input("掛米kg", value=75.0)
            with col2: j_name = st.selectbox("麹米", m_df['name'].tolist()); j_qty = st.number_input("麹米kg", value=40.0)
            with col3: s_name = st.selectbox("副原料", m_df['name'].tolist()); s_qty = st.number_input("副原料kg", value=10.0)
            
            k_p = m_df[m_df['name']==k_name]['unit_price'].values[0] if not m_df.empty else 0
            j_p = m_df[m_df['name']==j_name]['unit_price'].values[0] if not m_df.empty else 0
            s_p = m_df[m_df['name']==s_name]['unit_price'].values[0] if not m_df.empty else 0
            total_c = int((k_qty*k_p) + (j_qty*j_p) + (s_qty*s_p))
            st.metric("推定バッチ原価", f"¥ {total_c:,}")
            
            if st.form_submit_button("🚀 仕込み開始（在庫引き落とし）"):
                conn = get_connection(); cur = conn.cursor()
                for m, q in [(k_name, k_qty), (j_name, j_qty), (s_name, s_qty)]:
                    if q > 0: cur.execute("UPDATE materials SET stock = stock - %s WHERE name = %s", (q, m))
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (datetime.date.today(), f"仕込:{batch_name} ({k_name}他)", '仕掛品', '原材料', total_c))
                conn.commit(); cur.close(); conn.close(); st.success("記録しました")

elif menu == "📦 在庫管理":
    st.header("📦 在庫ステータス")
    t1, t2 = st.tabs(["🌾 原材料在庫", "🍾 製品在庫"])
    with t1:
        st.dataframe(load_data("materials")[['name', 'stock', 'unit', 'unit_price', 'memo']], use_container_width=True, hide_index=True)
        with st.expander("📥 原材料の入庫記録"):
            with st.form("in"):
                name = st.selectbox("原料", load_data("materials")['name'].tolist() if not load_data("materials").empty else ["なし"])
                qty = st.number_input("数量"); price = st.number_input("金額(円)")
                if st.form_submit_button("入庫反映"):
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute("UPDATE materials SET stock = stock + %s WHERE name = %s", (qty, name))
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (datetime.date.today(), f"入庫:{name}", '原材料', '現預金', price))
                    conn.commit(); cur.close(); conn.close(); st.toast("完了")
    with t2:
        st.dataframe(load_data("products"), use_container_width=True, hide_index=True)
        with st.expander("➕ 瓶詰め（仕掛品 → 製品）を記録"):
            with st.form("bottle"):
                p_df = load_data("products")
                target = st.selectbox("製品名", p_df['name'].tolist() if not p_df.empty else ["なし"])
                num = st.number_input("本数", value=100); cost = st.number_input("振替原価(円)", value=50000)
                if st.form_submit_button("🍾 瓶詰め完了"):
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute("UPDATE products SET stock = stock + %s WHERE name = %s", (num, target))
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (datetime.date.today(), f"瓶詰:{target}", '製品', '仕掛品', cost))
                    conn.commit(); cur.close(); conn.close()
                    st.success("在庫を更新しました！")

elif menu == "📈 利益分析":
    st.header("📈 限界利益シミュレーター")
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            p = st.number_input("販売価格(円)", value=2000, step=100)
            ml = st.number_input("容器の容量(ml)", value=720, step=10)
            m_c = st.number_input("原材料費/本(円)", value=295, step=50)
            p_c = st.number_input("資材費/本(円)", value=243, step=50)
            qty = st.number_input("予定本数", value=347, step=50)
            tax_rate = st.number_input("適用酒税(円/1L)", value=100, step=10)
            tax_b = int((ml / 1000) * tax_rate)
            profit = p - (m_c + p_c + tax_b)
        with c2:
            st.metric("1本当たりの利益", f"¥ {profit:,}")
            st.metric("バッチ総利益予測", f"¥ {profit * qty:,}")
            st.bar_chart(pd.DataFrame({"額": [p*qty, (m_c+p_c+tax_b)*qty, profit*qty]}, index=["売上高", "変動費", "限界利益"]))

elif menu == "📜 酒税帳簿":
    st.header("📜 酒税法定帳簿")
    t_df = load_data("tax_records")
    st.metric("今月の総出荷量", f"{t_df['total_liters'].sum() if not t_df.empty else 0} L")
    st.dataframe(t_df, use_container_width=True, hide_index=True)

elif menu == "📝 経理・マスタ":
    st.header("📝 経理・マスタ管理")
    t1, t2, t3, t4 = st.tabs(["💰 仕訳", "🌾 原材料", "🍾 製品", "🗑️ 削除"])
    
    with t1:
        acc = load_data("accounts")
        with st.form("j"):
            c1,c2,c3 = st.columns(3)
            d=c1.date_input("取引日"); db=c2.selectbox("借方", acc['name'].tolist()); cr=c3.selectbox("貸方", acc['name'].tolist())
            a=st.number_input("金額(円)", min_value=0); desc=st.text_input("摘要")
            if st.form_submit_button("登録"):
                conn=get_connection(); cur=conn.cursor(); cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s,%s,%s,%s,%s)", (d,desc,db,cr,a)); conn.commit(); cur.close(); conn.close()
        st.dataframe(load_data("journal_entries"), use_container_width=True)

    with t2:
        with st.form("m_reg"):
            n=st.text_input("原料名"); p=st.number_input("単価(円)", value=520); u=st.text_input("単位", value="kg"); s=st.number_input("初期在庫", value=0.0); memo=st.text_input("備考")
            if st.form_submit_button("マスタ登録"):
                conn=get_connection(); cur=conn.cursor(); cur.execute("INSERT INTO materials (name, unit_price, unit, stock, memo) VALUES (%s,%s,%s,%s,%s)", (n,p,u,s,memo)); conn.commit(); cur.close(); conn.close(); st.toast("登録完了")
        st.dataframe(load_data("materials"), use_container_width=True)

    with t3:
        with st.form("p"):
            n=st.text_input("製品名"); v=st.number_input("容量(ml)", value=720); p=st.number_input("定価(円)", value=2500)
            if st.form_submit_button("マスタ登録"):
                conn=get_connection(); cur=conn.cursor(); cur.execute("INSERT INTO products (name, volume_ml, price, stock) VALUES (%s,%s,%s,0)", (n,v,p)); conn.commit(); cur.close(); conn.close(); st.toast("登録完了")
        st.dataframe(load_data("products"), use_container_width=True)

    with t4:
        target_table = st.selectbox("削除するデータの種類", ["仕訳", "出荷帳簿", "原材料マスタ", "製品マスタ"])
        table_map = {"仕訳": "journal_entries", "出荷帳簿": "tax_records", "原材料マスタ": "materials", "製品マスタ": "products"}
        df_del = load_data(table_map[target_table])
        if not df_del.empty:
            options = []
            for _, r in df_del.iterrows():
                if target_table == "仕訳": text = f"[{r['date']}] {r['description']} (¥{r['amount']:,})"
                elif target_table == "出荷帳簿": text = f"[{r['date']}] {r['product_name']} {r['quantity']}本"
                elif target_table == "原材料マスタ": text = f"{r['name']} (単価:¥{r['unit_price']})"
                elif target_table == "製品マスタ": text = f"{r['name']} {r['volume_ml']}ml"
                options.append(f"ID:{r['id']} | {text}")
            selected_item = st.selectbox("削除するデータを選択", options)
            del_id = int(selected_item.split(" | ")[0].replace("ID:", ""))
            if st.button("🗑️ 完全削除", type="primary"):
                delete_record(table_map[target_table], del_id)
                st.success("削除しました！画面を更新してください。")
        else: st.info("データがありません。")

elif menu == "🔧 システム管理":
    st.header("🔧 システムメンテナンス")
    st.warning("【危険エリア】本番開始前のデータ一掃用です。")
    confirm_all = st.checkbox("すべてのデータ（取引・マスタ）を完全に消去します")
    if st.button("データベースを完全初期化", disabled=not confirm_all):
        conn = get_connection(); cur = conn.cursor()
        cur.execute("TRUNCATE TABLE journal_entries, tax_records, materials, products, loans RESTART IDENTITY")
        conn.commit(); cur.close(); conn.close()
        st.success("すべてのデータを消去しました。")
