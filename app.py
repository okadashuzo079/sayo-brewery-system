import streamlit as st
import pandas as pd
import psycopg2
import datetime

# ページの基本設定
st.set_page_config(page_title="醸造所システム (Cloud)", layout="wide")

# --- 接続設定 ---
# ⚠️ ここはご自身のパスワード入りのConnection Stringに必ず書き換えてください！
DB_URL = "postgresql://postgres.qoghpcgjweqyczbbcttj:19960519Tatsuki@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # テーブル作成群（省略せずに実行）
    cur.execute('CREATE TABLE IF NOT EXISTS materials (id SERIAL PRIMARY KEY, name TEXT, unit TEXT, memo TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS accounts (id SERIAL PRIMARY KEY, code TEXT, name TEXT, type TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS journal_entries (id SERIAL PRIMARY KEY, date DATE, description TEXT, debit_account TEXT, credit_account TEXT, amount INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS loans (id SERIAL PRIMARY KEY, lender TEXT, principal BIGINT, interest_rate REAL)')
    
    # 仕掛品（製造途中の資産）の勘定科目を追加するための処理
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

st.title("醸造所 管理ダッシュボード 🍺")
st.info("データはクラウドデータベース(Supabase)と同期されています。")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 データベース", "🧪 製造・仕込み(自動化)", "📝 データ登録", "💰 会計記帳", "📈 財務レポート"
])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🌾 原材料マスタ")
        st.dataframe(load_data("materials"), hide_index=True)
    with col2:
        st.subheader("🏦 借入金情報")
        st.dataframe(load_data("loans"), hide_index=True)

# --- ★今回大きく進化した「製造・仕込み」タブ ---
with tab2:
    st.subheader("🚀 仕込み作業と会計の自動連動")
    st.write("現場で仕込みを入力すると、自動的に「仕掛品（製造中の価値）」として会計帳簿に記録されます。")
    
    materials_df = load_data("materials")
    mat_names = materials_df['name'].tolist() if not materials_df.empty else ["原材料が未登録です"]
    
    with st.form("brew_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            target_mat = st.selectbox("使用する原材料", mat_names)
            amount = st.number_input("使用量", min_value=1, value=10)
        with col2:
            # 簡略化のため、今回は原価を手入力または固定値にします
            unit_price = st.number_input("1単位あたりの原価（円）", min_value=0, value=800)
            total_cost = amount * unit_price
            st.metric("📊 今回の仕込み原価", f"{total_cost:,} 円")
            
        if st.form_submit_button("🔨 仕込みを開始する（帳簿へ自動連動）"):
            conn = get_connection()
            cur = conn.cursor()
            
            # 本日の日付を取得
            today = datetime.date.today().strftime("%Y-%m-%d")
            desc = f"【自動連動】{target_mat} {amount} を仕込み"
            
            # 自動仕訳の実行（借方: 仕掛品 / 貸方: 原材料）
            cur.execute("""
                INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) 
                VALUES (%s, %s, %s, %s, %s)
            """, (today, desc, '仕掛品', '原材料', total_cost))
            
            conn.commit()
            cur.close()
            conn.close()
            st.success(f"大成功！「{target_mat}」の仕込みを記録し、会計帳簿に {total_cost:,}円 を自動計上しました。")

with tab3:
    st.subheader("新しい原材料の登録")
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
            st.success(f"「{n}」を保存しました。")

with tab4:
    st.subheader("日々の取引を記録する（手動）")
    df_acc = load_data("accounts")
    with st.form("j_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1: date = st.date_input("取引日")
        with col2: debit = st.selectbox("借方", df_acc['name'].tolist())
        with col3: credit = st.selectbox("貸方", df_acc['name'].tolist())
        amt = st.number_input("金額（円）", min_value=0, step=1000)
        desc = st.text_input("摘要")
        if st.form_submit_button("仕訳登録"):
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO journal_entries (date, description, debit_account, credit_account, amount) VALUES (%s, %s, %s, %s, %s)",
                       (date, desc, debit, credit, amt))
            conn.commit()
            cur.close()
            conn.close()
            st.success("仕訳を記録しました。")
    st.dataframe(load_data("journal_entries"), hide_index=True)

with tab5:
    st.subheader("リアルタイム経営状況")
    df_j = load_data("journal_entries")
    if not df_j.empty:
        c_in = df_j[df_j['debit_account'] == '現預金']['amount'].sum()
        c_out = df_j[df_j['credit_account'] == '現預金']['amount'].sum()
        st.metric("💰 現在の現預金残高", f"{c_in - c_out:,} 円")
        
        # 勘定科目別の合計をグラフ表示
        debit_sum = df_j.groupby('debit_account')['amount'].sum().reset_index()
        debit_sum.columns = ['勘定科目', '金額']
        st.write("📊 資産・費用の増加内訳")
        st.bar_chart(debit_sum.set_index('勘定科目'))
