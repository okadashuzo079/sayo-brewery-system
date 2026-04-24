import streamlit as st
import pandas as pd
import psycopg2
import datetime

# --- ページの基本設定（ここも少し洗練させました） ---
st.set_page_config(page_title="Sayo Brewery 🍺", page_icon="🌾", layout="centered")

# --- 接続設定 ---
# ⚠️ ここはご自身のパスワードとプロジェクトID入りのConnection Stringに必ず書き換えてください！
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

# タイトルを少しオシャレに
st.title("Sayo Brewery Dashboard 🍺")
st.caption("クラウド同期中 🟢")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 マスタ", "🧪 製造", "📝 登録", "💰 会計", "📈 財務"
])

with tab1:
    st.subheader("🌾 原材料 & 🏦 借入金")
    st.dataframe(load_data("materials"), hide_index=True, use_container_width=True)
    st.dataframe(load_data("loans"), hide_index=True, use_container_width=True)

with tab2:
    st.subheader("🚀 製造・仕込み記録")
    
    materials_df = load_data("materials")
    mat_names = materials_df['name'].tolist() if not materials_df.empty else ["原材料が未登録です"]
    
    # ★変更点1：入力フォームを折りたたみ式にしてスッキリ！
    with st.expander("➕ 新しい仕込みを記録する", expanded=False):
        with st.form("brew_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                target_mat = st.selectbox("使用する原材料", mat_names)
                amount = st.number_input("使用量", min_value=1, value=10)
            with col2:
                unit_price = st.number_input("1単位の原価（円）", min_value=0, value=800)
                total_cost = amount * unit_price
                st.metric("📊 仕込み原価", f"{total_cost:,} 円")
                
            if st.form_submit_button("🔨 仕込みを開始する"):
                conn = get_connection()
                cur = conn.cursor()
                today = datetime.date.today().strftime("%Y-%m-%d")
                desc = f"【製造】{target_mat} {amount} を仕込み"
                
                cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)", 
                            (today, desc, '仕掛品', '原材料', total_cost))
                conn.commit()
                cur.close()
                conn.close()
                
                # ★変更点2＆3：スマホ風の通知とお祝いの風船！
                st.toast(f"大成功！「{target_mat}」の仕込みを記録しました！", icon="🍻")
                st.balloons()

with tab3:
    st.subheader("新しい原材料の登録")
    with st.expander("➕ マスタに原材料を追加", expanded=False):
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
                st.toast(f"「{n}」を保存しました！", icon="✅")

with tab4:
    st.subheader("日々の取引記録")
    df_acc = load_data("accounts")
    with st.expander("➕ 新しい仕訳を登録", expanded=False):
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

with tab5:
    st.subheader("リアルタイム経営状況")
    df_j = load_data("journal_entries")
    if not df_j.empty:
        c_in = df_j[df_j['debit_account'] == '現預金']['amount'].sum()
        c_out = df_j[df_j['credit_account'] == '現預金']['amount'].sum()
        st.metric("💰 現在の現預金残高", f"{c_in - c_out:,} 円")
        
        debit_sum = df_j.groupby('debit_account')['amount'].sum().reset_index()
        debit_sum.columns = ['勘定科目', '金額']
        st.write("📊 資産・費用の増加内訳")
        st.bar_chart(debit_sum.set_index('勘定科目'))
