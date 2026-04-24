import streamlit as st
import pandas as pd
import psycopg2
import datetime

# --- ページの基本設定（さらに洗練されたアプリ風に） ---
st.set_page_config(page_title="Sayo Brewery 🍺", page_icon="🌾", layout="wide", initial_sidebar_state="expanded")

# --- 接続設定 ---
# ⚠️ プロジェクトID・パスワード設定済みの確実なURLです
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
    cur.execute("SELECT * FROM accounts WHERE name = '仕掛品'")
    if not cur.fetchone():
        cur.execute("INSERT INTO accounts (code, name, type) VALUES ('120', '仕掛品', '資産')")
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
# ★ 最新デザイン：サイドバー・ナビゲーション
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3075/3075908.png", width=50) # ビールのアイコン
    st.title("Sayo Brewery")
    st.caption("v2.0 Professional Edition")
    st.divider()
    
    # ラジオボタンでメニューをスッキリ切り替え
    menu = st.radio(
        "📂 メニュー",
        ("🏠 ホーム (KPI)", "🧪 製造・仕込み", "📊 酒税シミュレーター", "📝 経理・マスタ管理"),
        label_visibility="collapsed"
    )
    st.divider()
    st.success("🟢 クラウド同期中")

# ==========================================
# 画面ごとのコンテンツ
# ==========================================

if menu == "🏠 ホーム (KPI)":
    st.header("🏠 ホーム (ダッシュボード)")
    st.write("現在の経営状況を俯瞰します。")
    
    df_j = load_data("journal_entries")
    
    # ★ 最新トレンド：KPIカードの配置
    col1, col2, col3 = st.columns(3)
    
    if not df_j.empty:
        c_in = df_j[df_j['debit_account'] == '現預金']['amount'].sum()
        c_out = df_j[df_j['credit_account'] == '現預金']['amount'].sum()
        cash = c_in - c_out
        
        assets = df_j[df_j['debit_account'] == '仕掛品']['amount'].sum()
    else:
        cash = 0
        assets = 0
        
    with col1:
        st.metric(label="💰 現預金残高", value=f"¥ {cash:,}")
    with col2:
        st.metric(label="🌾 製造中資産 (仕掛品)", value=f"¥ {assets:,}")
    with col3:
        st.metric(label="📅 次回製造予定", value="2026年10月")

    st.divider()
    st.subheader("直近の取引履歴")
    if not df_j.empty:
        st.dataframe(df_j.tail(5), hide_index=True, use_container_width=True)

elif menu == "🧪 製造・仕込み":
    st.header("🧪 製造・仕込みの記録")
    st.write("製造記録と会計帳簿を自動連動させます。")
    
    materials_df = load_data("materials")
    mat_names = materials_df['name'].tolist() if not materials_df.empty else ["原材料が未登録です"]
    
    with st.container(border=True):
        with st.form("brew_form", clear_on_submit=True):
            st.subheader("➕ 新しいバッチを仕込む")
            col1, col2 = st.columns(2)
            with col1:
                target_mat = st.selectbox("主原料", mat_names)
                amount = st.number_input("使用量", min_value=1.0, value=10.0)
            with col2:
                unit_price = st.number_input("1単位の原価（円）", min_value=0, value=800)
                total_cost = int(amount * unit_price)
                st.metric("📊 今回の原価計上", f"¥ {total_cost:,}")
                
            if st.form_submit_button("🚀 仕込み開始 (帳簿へ連動)", type="primary"):
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
                st.balloons()

elif menu == "📊 酒税シミュレーター":
    st.header("📊 酒税シミュレーター (その他の醸造酒)")
    st.write("製造予定量から、納税予定の酒税を自動計算します。")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            vol = st.number_input("製造予定量 (リットル)", min_value=0, value=500, step=10)
        with col2:
            # その他の醸造酒の概算税率 (※実際の2026年税率に合わせて微調整可能)
            tax_rate_per_liter = 140 
            st.info(f"適用税率: 1リットルあたり {tax_rate_per_liter}円")
            
        tax_amount = vol * tax_rate_per_liter
        st.metric(label="⚠️ 納税予定額 (概算)", value=f"¥ {tax_amount:,}")
        st.progress(min(tax_amount / 1000000, 1.0), text="酒税負担の可視化")

elif menu == "📝 経理・マスタ管理":
    st.header("📝 経理・マスタ管理")
    
    tab_a, tab_b = st.tabs(["💰 日々の仕訳入力", "🌾 マスタ登録"])
    
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
                st.toast("仕訳を帳簿に記録しました！", icon="📓")
                
        st.dataframe(load_data("journal_entries"), hide_index=True, use_container_width=True)
        
    with tab_b:
        with st.form("mat_form", clear_on_submit=True):
            n = st.text_input("原材料名")
            u = st.selectbox("単位", ["kg", "g", "L", "個"])
            m = st.text_input("メモ")
            if st.form_submit_button("原材料を登録"):
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO materials (name, unit, memo) VALUES (%s, %s, %s)", (n, u, m))
                conn.commit()
                cur.close()
                conn.close()
                st.toast(f"「{n}」を保存しました！", icon="✅")
        st.dataframe(load_data("materials"), hide_index=True, use_container_width=True)
