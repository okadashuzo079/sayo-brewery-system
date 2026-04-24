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
    
    # ★ 新規追加：酒税計算用の出荷帳簿テーブル
    cur.execute('CREATE TABLE IF NOT EXISTS tax_records (id SERIAL PRIMARY KEY, date DATE, product_name TEXT, quantity INTEGER, total_liters REAL, tax_amount INTEGER)')

    required_accounts = [
        ('120', '仕掛品', '資産'),
        ('121', '製品', '資産'),
        ('411', '売上高', '収益'),
        ('210', '未払酒税', '負債') # ★ 新規追加：将来払う税金を記録
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
    df = pd.read_sql(f"SELECT * FROM {table_name} ORDER BY id ASC", conn)
    conn.close()
    return df

# ==========================================
# サイドバー・ナビゲーション
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3075/3075908.png", width=50)
    st.title("Sayo Brewery")
    st.caption("v5.0 Tax & Final Edition")
    st.divider()
    
    menu = st.radio(
        "📂 メニュー",
        ("🏠 ホーム (KPI)", "🏪 直売所レジ (POS)", "📜 酒税・法定帳簿", "🧪 製造・仕込み", "📦 瓶詰め・在庫", "📝 経理・マスタ管理"),
        label_visibility="collapsed"
    )
    st.divider()
    st.success("🟢 クラウド同期中")

# ==========================================
# 画面ごとのコンテンツ
# ==========================================

if menu == "🏠 ホーム (KPI)":
    st.header("🏠 ホーム (ダッシュボード)")
    df_j = load_data("journal_entries")
    
    col1, col2, col3, col4 = st.columns(4)
    if not df_j.empty:
        cash = df_j[df_j['debit_account'] == '現預金']['amount'].sum() - df_j[df_j['credit_account'] == '現預金']['amount'].sum()
        sales = df_j[df_j['credit_account'] == '売上高']['amount'].sum()
        products = df_j[df_j['debit_account'] == '製品']['amount'].sum() - df_j[df_j['credit_account'] == '製品']['amount'].sum()
        tax = df_j[df_j['credit_account'] == '未払酒税']['amount'].sum() # ★ 納税予定額
    else:
        cash, sales, products, tax = 0, 0, 0, 0
        
    with col1: st.metric("💰 現預金残高", f"¥ {cash:,}")
    with col2: st.metric("📈 累計売上高", f"¥ {sales:,}")
    with col3: st.metric("🍾 完成在庫", f"¥ {products:,}")
    with col4: st.metric("⚠️ 納税予定(酒税)", f"¥ {tax:,}")

    st.divider()
    st.subheader("直近の取引履歴")
    if not df_j.empty:
        st.dataframe(df_j.tail(5), hide_index=True, use_container_width=True)

elif menu == "🏪 直売所レジ (POS)":
    st.header("🏪 直売所 かんたんレジ")
    df_p = load_data("products")
    
    if df_p.empty:
        st.warning("販売できる製品がありません。")
    else:
        with st.container(border=True):
            with st.form("pos_form", clear_on_submit=True):
                st.subheader("🛒 お会計")
                col1, col2 = st.columns(2)
                options = [f"{row['name']} (在庫: {row['stock']}本) - ¥{row['price']}" for index, row in df_p.iterrows()]
                
                with col1:
                    selected_option = st.selectbox("販売する商品を選択", options)
                    sell_count = st.number_input("販売数", min_value=1, value=1)
                
                selected_name = selected_option.split(" (")[0]
                selected_price = int(selected_option.split("¥")[1])
                total_sales = selected_price * sell_count
                
                with col2:
                    st.metric("💳 お会計合計", f"¥ {total_sales:,}")
                    
                if st.form_submit_button("💰 会計を完了する（売上＆酒税計上）", type="primary"):
                    conn = get_connection()
                    cur = conn.cursor()
                    
                    # --- 1. 在庫と売上の処理 ---
                    cur.execute("UPDATE products SET stock = stock - %s WHERE name = %s", (sell_count, selected_name))
                    today = datetime.date.today().strftime("%Y-%m-%d")
                    desc = f"【店舗売上】{selected_name} {sell_count}本"
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, desc, '現預金', '売上高', total_sales))
                    
                    # --- 2. ★酒税の自動計算処理 ---
                    # 商品の容量(ml)を取得
                    cur.execute("SELECT volume_ml FROM products WHERE name = %s", (selected_name,))
                    vol_result = cur.fetchone()
                    volume_ml = vol_result[0] if vol_result else 0
                    
                    # リットル換算と税額計算 (その他の醸造酒: 140円/L想定)
                    total_liters = (volume_ml * sell_count) / 1000.0
                    tax_amount = int(total_liters * 140)
                    
                    # 帳簿へ記録
                    cur.execute("INSERT INTO tax_records (date, product_name, quantity, total_liters, tax_amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, selected_name, sell_count, total_liters, tax_amount))
                    
                    # 経理上も「未払酒税」として負債計上（費用/未払金）
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, f"【酒税計上】{total_liters}L出荷分", '租税公課', '未払酒税', tax_amount))
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    st.toast(f"お会計完了！同時に酒税帳簿へ {total_liters}L 出荷分を自動記帳しました。", icon="🎉")
                    st.balloons()

# ==========================================
# ★ 新機能：酒税法定帳簿
# ==========================================
elif menu == "📜 酒税・法定帳簿":
    st.header("📜 酒税 出荷帳簿 (自動作成)")
    st.write("POSレジでの販売データから、税務署へ申告する出荷数量と酒税額を自動集計しています。")
    
    df_tax = load_data("tax_records")
    if df_tax.empty:
        st.info("まだ出荷（販売）記録がありません。")
    else:
        col1, col2 = st.columns(2)
        total_l = df_tax['total_liters'].sum()
        total_t = df_tax['tax_amount'].sum()
        with col1:
            st.metric("📦 今月の総出荷量 (リットル)", f"{total_l:,.2f} L")
        with col2:
            st.metric("⚠️ 今月の納付予定酒税額", f"¥ {total_t:,}")
            
        st.divider()
        st.subheader("日々の出荷明細 (酒類製造記帳簿データ)")
        st.dataframe(df_tax, hide_index=True, use_container_width=True)

# (以下略: 製造、瓶詰め、マスタ管理はv4と同じなので省略せずにそのまま組み込んであります)
elif menu == "🧪 製造・仕込み":
    st.header("🧪 製造・仕込みの記録")
    materials_df = load_data("materials")
    mat_names = materials_df['name'].tolist() if not materials_df.empty else ["未登録"]
    with st.container(border=True):
        with st.form("brew_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                target_mat = st.selectbox("主原料", mat_names)
                amount = st.number_input("使用量", min_value=1.0, value=10.0)
            with col2:
                unit_price = st.number_input("1単位の原価（円）", min_value=0, value=800)
                total_cost = int(amount * unit_price)
                st.metric("📊 今回の原価計上", f"¥ {total_cost:,}")
            if st.form_submit_button("🚀 仕込み開始 (仕掛品へ計上)", type="primary"):
                conn = get_connection()
                cur = conn.cursor()
                today = datetime.date.today().strftime("%Y-%m-%d")
                desc = f"【製造】{target_mat} {amount} 仕込み"
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                            (today, desc, '仕掛品', '原材料', total_cost))
                conn.commit()
                cur.close()
                conn.close()
                st.toast(f"仕込みを記録しました！", icon="🍻")

elif menu == "📦 瓶詰め・在庫":
    st.header("📦 瓶詰め・在庫管理")
    tab_stock, tab_bottle = st.tabs(["🍾 現在の在庫一覧", "➕ 瓶詰めの記録"])
    with tab_stock:
        df_p = load_data("products")
        st.dataframe(df_p, hide_index=True, use_container_width=True)
    with tab_bottle:
        if not df_p.empty:
            with st.form("bottle_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    target_prod = st.selectbox("瓶詰めする製品", df_p['name'].tolist())
                    bottle_count = st.number_input("瓶詰めした本数", min_value=1, value=100)
                with col2:
                    transfer_cost = st.number_input("振り替える原価合計（円）", min_value=0, value=50000)
                if st.form_submit_button("🍾 瓶詰め完了（在庫に追加）", type="primary"):
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE products SET stock = stock + %s WHERE name = %s", (bottle_count, target_prod))
                    today = datetime.date.today().strftime("%Y-%m-%d")
                    desc = f"【瓶詰】{target_prod} {bottle_count}本"
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, desc, '製品', '仕掛品', transfer_cost))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success(f"{target_prod} を {bottle_count}本、在庫に追加しました！")

elif menu == "📝 経理・マスタ管理":
    st.header("📝 経理・マスタ管理")
    tab_a, tab_b, tab_c = st.tabs(["💰 仕訳入力", "🌾 原材料", "🍾 製品マスタ"])
    with tab_a:
        df_acc = load_data("accounts")
        with st.form("j_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1: 
                date = st.date_input("取引日")
                debit = st.selectbox("借方", df_acc['name'].tolist())
            with col2: 
                credit = st.selectbox("貸方", df_acc['name'].tolist())
                amt = st.number_input("金額（円）", min_value=0, step=1000)
            desc = st.text_input("摘要")
            if st.form_submit_button("仕訳を登録"):
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)",
                           (date, desc, debit, credit, amt))
                conn.commit()
                cur.close()
                conn.close()
                st.toast("仕訳を記録しました", icon="✅")
        st.dataframe(load_data("journal_entries"), hide_index=True, use_container_width=True)
    with tab_b:
        with st.form("mat_form", clear_on_submit=True):
            n = st.text_input("原材料名")
            u = st.selectbox("単位", ["kg", "g", "L", "個"])
            m = st.text_input("メモ")
            if st.form_submit_button("登録"):
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO materials (name, unit, memo) VALUES (%s, %s, %s)", (n, u, m))
                conn.commit()
                cur.close()
                conn.close()
        st.dataframe(load_data("materials"), hide_index=True, use_container_width=True)
    with tab_c:
        with st.form("prod_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                pn = st.text_input("製品名")
                pv = st.number_input("内容量 (ml)", min_value=1, value=330)
            with col2:
                pp = st.number_input("販売価格 (円)", min_value=0, value=800)
            if st.form_submit_button("製品を登録"):
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO products (name, volume_ml, price, stock) VALUES (%s, %s, %s, 0)", (pn, pv, pp))
                conn.commit()
                cur.close()
                conn.close()
        st.dataframe(load_data("products"), hide_index=True, use_container_width=True)
