import streamlit as st
import pandas as pd
import psycopg2
import datetime

# --- ページの基本設定 ---
st.set_page_config(page_title="Sayo Brewery 🍺", page_icon="🌾", layout="wide", initial_sidebar_state="expanded")

# --- 接続設定 ---
# ⚠️ プロジェクトID・パスワード設定済みの確実なURL
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

    # 自動で必要な勘定科目を追加する処理
    required_accounts = [
        ('120', '仕掛品', '資産'),
        ('121', '製品', '資産'),
        ('411', '売上高', '収益') # ★ 新規追加：商品を売った時の「売上」を記録する科目
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
    st.caption("v4.0 POS & Retail Edition")
    st.divider()
    
    # ★ メニューの2番目に「直売所レジ」を配置してアクセスしやすくしました
    menu = st.radio(
        "📂 メニュー",
        ("🏠 ホーム (KPI)", "🏪 直売所レジ (POS)", "🧪 製造・仕込み", "📦 瓶詰め・在庫", "📊 酒税シミュレーター", "📝 経理・マスタ管理"),
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
    
    col1, col2, col3 = st.columns(3)
    if not df_j.empty:
        c_in = df_j[df_j['debit_account'] == '現預金']['amount'].sum()
        c_out = df_j[df_j['credit_account'] == '現預金']['amount'].sum()
        cash = c_in - c_out
        
        # 売上高の合計を計算
        sales = df_j[df_j['credit_account'] == '売上高']['amount'].sum()
        
        products = df_j[df_j['debit_account'] == '製品']['amount'].sum() - df_j[df_j['credit_account'] == '製品']['amount'].sum()
    else:
        cash, sales, products = 0, 0, 0
        
    with col1: st.metric("💰 現預金残高", f"¥ {cash:,}")
    with col2: st.metric("📈 累計売上高", f"¥ {sales:,}")
    with col3: st.metric("🍾 完成在庫 (製品)", f"¥ {products:,}")

    st.divider()
    st.subheader("直近の取引履歴")
    if not df_j.empty:
        st.dataframe(df_j.tail(5), hide_index=True, use_container_width=True)

# ==========================================
# ★ 新機能：直売所 POSレジ
# ==========================================
elif menu == "🏪 直売所レジ (POS)":
    st.header("🏪 直売所 かんたんレジ")
    st.write("iPadやスマホから、販売の記録をワンタッチで行います。（在庫と売上が自動連動します）")
    
    df_p = load_data("products")
    if df_p.empty:
        st.warning("販売できる製品がありません。先に製品マスタを登録してください。")
    else:
        with st.container(border=True):
            with st.form("pos_form", clear_on_submit=True):
                st.subheader("🛒 お会計")
                col1, col2 = st.columns(2)
                
                # 選択肢の作成（商品名、在庫数、価格をひと目で分かるようにする）
                options = [f"{row['name']} (在庫: {row['stock']}本) - ¥{row['price']}" for index, row in df_p.iterrows()]
                
                with col1:
                    selected_option = st.selectbox("販売する商品を選択", options)
                    sell_count = st.number_input("販売数", min_value=1, value=1)
                
                # 文字列から商品名と価格を抽出して計算
                selected_name = selected_option.split(" (")[0]
                selected_price = int(selected_option.split("¥")[1])
                total_sales = selected_price * sell_count
                
                with col2:
                    st.metric("💳 お会計合計", f"¥ {total_sales:,}")
                    st.write(f"※販売後、自動で在庫から {sell_count}本 マイナスされます。")
                    
                if st.form_submit_button("💰 会計を完了する（売上計上）", type="primary"):
                    conn = get_connection()
                    cur = conn.cursor()
                    
                    # 1. 在庫を減らす
                    cur.execute("UPDATE products SET stock = stock - %s WHERE name = %s", (sell_count, selected_name))
                    
                    # 2. 売上の仕訳（借方：現預金 / 貸方：売上高）
                    today = datetime.date.today().strftime("%Y-%m-%d")
                    desc = f"【店舗売上】{selected_name} {sell_count}本"
                    cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                                (today, desc, '現預金', '売上高', total_sales))
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    st.toast(f"毎度ありがとうございます！ {selected_name} が {sell_count}本 売れました！", icon="🎉")
                    st.balloons()

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
                st.toast(f"「{target_mat}」の仕込みを記録しました！", icon="🍻")

elif menu == "📦 瓶詰め・在庫":
    st.header("📦 瓶詰め・在庫管理")
    tab_stock, tab_bottle = st.tabs(["🍾 現在の在庫一覧", "➕ 瓶詰めの記録（仕掛品→製品）"])
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

elif menu == "📊 酒税シミュレーター":
    st.header("📊 酒税シミュレーター")
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1: vol = st.number_input("製造予定量 (リットル)", min_value=0, value=500, step=10)
        with col2:
            tax_rate_per_liter = 140 
            st.info(f"適用税率: 1Lあたり {tax_rate_per_liter}円")
        st.metric("⚠️ 納税予定額 (概算)", f"¥ {vol * tax_rate_per_liter:,}")

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
