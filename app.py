import streamlit as st
import pandas as pd
import psycopg2
import datetime

# --- ページの基本設定 ---
st.set_page_config(page_title="Sayo Brewery 🍺", page_icon="🌾", layout="wide", initial_sidebar_state="expanded")

# --- 接続設定 ---
# ⚠️ 岡田様にご確認いただいた正解のURLです
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

    required_accounts = [
        ('120', '仕掛品', '資産'),
        ('121', '製品', '資産'),
        ('411', '売上高', '収益'),
        ('210', '未払酒税', '負債'),
        ('511', '租税公課', '費用')
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
    st.caption("v6.0 Profit Analysis Edition")
    st.divider()
    
    menu = st.radio(
        "📂 メニュー",
        ("🏠 ホーム (KPI)", "🏪 直売所レジ (POS)", "📈 限界利益シミュレーター", "📜 酒税・法定帳簿", "🧪 製造・仕込み", "📦 瓶詰め・在庫", "📝 経理・マスタ管理"),
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
        tax = df_j[df_j['credit_account'] == '未払酒税']['amount'].sum()
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

# ==========================================
# ★ 新機能：限界利益シミュレーター
# ==========================================
elif menu == "📈 限界利益シミュレーター":
    st.header("📈 バッチ別 限界利益分析")
    st.write("この仕込みでどれくらいの利益が出るか、事前にシミュレーションします。")
    
    with st.container(border=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("条件設定")
            price = st.number_input("1本当たりの販売価格 (円)", min_value=0, value=2000)
            vol_ml = st.selectbox("容器サイズ", [330, 500, 750], index=0)
            mat_cost = st.number_input("1本当たりの原材料費 (円)", min_value=0, value=300)
            pack_cost = st.number_input("1本当たりの消耗品費 (瓶・栓など)", min_value=0, value=150)
            count = st.number_input("製造本数 (本)", min_value=1, value=500)
            
            # 酒税計算 (140円/L)
            tax_per_bottle = int((vol_ml / 1000) * 140)
            
            # 変動費合計
            variable_cost_per_unit = mat_cost + pack_cost + tax_per_bottle
            marginal_profit_per_unit = price - variable_cost_per_unit
            total_sales = price * count
            total_variable_cost = variable_cost_per_unit * count
            total_profit = marginal_profit_per_unit * count
            profit_ratio = (marginal_profit_per_unit / price * 100) if price > 0 else 0

        with col2:
            st.subheader("分析結果")
            res_c1, res_c2, res_c3 = st.columns(3)
            res_c1.metric("1本当たりの利益", f"¥ {marginal_profit_per_unit:,}")
            res_c2.metric("バッチ総利益", f"¥ {total_profit:,}")
            res_c3.metric("限界利益率", f"{profit_ratio:.1f} %")
            
            # グラフ表示
            chart_data = pd.DataFrame({
                "カテゴリー": ["売上高", "変動費", "限界利益"],
                "金額": [total_sales, total_variable_cost, total_profit]
            })
            st.bar_chart(chart_data.set_index("カテゴリー"))
            
            st.info(f"💡 酒税は1本当たり 約{tax_per_bottle}円 含まれています。")

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
                    selected_option = st.selectbox("商品を選択", options)
                    sell_count = st.number_input("販売数", min_value=1, value=1)
                selected_name = selected_option.split(" (")[0]
                selected_price = int(selected_option.split("¥")[1])
                total_sales = selected_price * sell_count
                with col2:
                    st.metric("💳 お会計合計", f"¥ {total_sales:,}")
                if st.form_submit_button("💰 会計を完了する", type="primary"):
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE products SET stock = stock - %s WHERE name = %s", (sell_count, selected_name))
                    cur.execute("SELECT volume_ml FROM products WHERE name = %s", (selected_name,))
                    vol_ml = cur.fetchone()[0]
                    today = datetime.date.today().strftime("%Y-%m-%d")
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, f"【店舗売上】{selected_name} {sell_count}本", '現預金', '売上高', total_sales))
                    total_l = (vol_ml * sell_count) / 1000.0
                    tax_amt = int(total_l * 140)
                    cur.execute("INSERT INTO tax_records (date, product_name, quantity, total_liters, tax_amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, selected_name, sell_count, total_l, tax_amt))
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, f"【酒税計上】{total_l}L出荷分", '租税公課', '未払酒税', tax_amt))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.toast("お会計完了！", icon="🎉")
                    st.balloons()

elif menu == "📜 酒税・法定帳簿":
    st.header("📜 酒税 出荷帳簿")
    df_tax = load_data("tax_records")
    if not df_tax.empty:
        col1, col2 = st.columns(2)
        with col1: st.metric("📦 今月の総出荷量", f"{df_tax['total_liters'].sum():,.2f} L")
        with col2: st.metric("⚠️ 納付予定酒税額", f"¥ {df_tax['tax_amount'].sum():,}")
        st.dataframe(df_tax, hide_index=True, use_container_width=True)

elif menu == "🧪 製造・仕込み":
    st.header("🧪 製造・仕込みの記録")
    m_df = load_data("materials")
    with st.form("brew_form", clear_on_submit=True):
        mat = st.selectbox("主原料", m_df['name'].tolist() if not m_df.empty else ["未登録"])
        amt = st.number_input("使用量", min_value=1.0, value=10.0)
        u_p = st.number_input("1単位の原価（円）", min_value=0, value=800)
        cost = int(amt * u_p)
        if st.form_submit_button("🚀 仕込み開始"):
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                        (datetime.date.today().strftime("%Y-%m-%d"), f"【製造】{mat} {amt} 仕込み", '仕掛品', '原材料', cost))
            conn.commit()
            cur.close()
            conn.close()
            st.toast("仕込みを記録！")

elif menu == "📦 瓶詰め・在庫":
    st.header("📦 瓶詰め・在庫管理")
    df_p = load_data("products")
    tab1, tab2 = st.tabs(["🍾 在庫一覧", "➕ 瓶詰め"])
    with tab1: st.dataframe(df_p, hide_index=True, use_container_width=True)
    with tab2:
        with st.form("bottle_form", clear_on_submit=True):
            prod = st.selectbox("製品", df_p['name'].tolist() if not df_p.empty else ["なし"])
            b_cnt = st.number_input("本数", min_value=1, value=100)
            t_cost = st.number_input("振替原価", min_value=0, value=50000)
            if st.form_submit_button("🍾 完了"):
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("UPDATE products SET stock = stock + %s WHERE name = %s", (b_cnt, prod))
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                            (datetime.date.today().strftime("%Y-%m-%d"), f"【瓶詰】{prod} {b_cnt}本", '製品', '仕掛品', t_cost))
                conn.commit()
                cur.close()
                conn.close()
                st.success("在庫に追加しました！")

elif menu == "📝 経理・マスタ管理":
    st.header("📝 経理・マスタ管理")
    t1, t2, t3 = st.tabs(["💰 仕訳", "🌾 原材料", "🍾 製品"])
    with t1:
        df_acc = load_data("accounts")
        with st.form("j"):
            d = st.date_input("日"); db = st.selectbox("借", df_acc['name'].tolist()); cr = st.selectbox("貸", df_acc['name'].tolist()); a = st.number_input("円"); desc = st.text_input("摘")
            if st.form_submit_button("登録"):
                conn = get_connection(); cur = conn.cursor(); cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", (d, desc, db, cr, a)); conn.commit(); cur.close(); conn.close()
        st.dataframe(load_data("journal_entries"), hide_index=True)
    with t2:
        with st.form("m"):
            n = st.text_input("名"); u = st.selectbox("単", ["kg", "L", "個"]); m = st.text_input("メモ")
            if st.form_submit_button("登録"):
                conn = get_connection(); cur = conn.cursor(); cur.execute("INSERT INTO materials (name, unit, memo) VALUES (%s, %s, %s)", (n, u, m)); conn.commit(); cur.close(); conn.close()
        st.dataframe(load_data("materials"), hide_index=True)
    with t3:
        with st.form("p"):
            n = st.text_input("製品名"); v = st.number_input("ml", value=330); p = st.number_input("価格", value=800)
            if st.form_submit_button("登録"):
                conn = get_connection(); cur = conn.cursor(); cur.execute("INSERT INTO products (name, volume_ml, price, stock) VALUES (%s, %s, %s, 0)", (n, v, p)); conn.commit(); cur.close(); conn.close()
        st.dataframe(load_data("products"), hide_index=True)
