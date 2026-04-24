import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

# ページの基本設定
st.set_page_config(page_title="醸造所システム (Cloud)", layout="wide")

# --- 接続設定 ---
# 下の引用符の中に、ご自身のConnection String（パスワード反映済み）を貼り付けてください
DB_URL = "postgresql://postgres.qoghpcgjweqyczbbcttj:19960519Tatsuki@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

# データベース接続関数
def get_connection():
    return psycopg2.connect(DB_URL)

# 初期テーブル作成（クラウド金庫が空の場合に一度だけ実行）
def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # 原材料テーブル
    cur.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id SERIAL PRIMARY KEY,
            name TEXT,
            unit TEXT,
            memo TEXT
        )
    ''')
    # 勘定科目テーブル
    cur.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            code TEXT,
            name TEXT,
            type TEXT
        )
    ''')
    # 仕訳テーブル
    cur.execute('''
        CREATE TABLE IF NOT EXISTS journal_entries (
            id SERIAL PRIMARY KEY,
            date DATE,
            description TEXT,
            debit_account TEXT,
            credit_account TEXT,
            amount INTEGER
        )
    ''')
    # 借入金テーブル（初期化）
    cur.execute('''
        CREATE TABLE IF NOT EXISTS loans (
            id SERIAL PRIMARY KEY,
            lender TEXT,
            principal BIGINT,
            interest_rate REAL
        )
    ''')
    
    # 初期データの投入（データが空の場合のみ）
    cur.execute("SELECT COUNT(*) FROM accounts")
    if cur.fetchone()[0] == 0:
        accounts = [
            ('100', '現預金', '資産'),
            ('110', '原材料', '資産'),
            ('200', '借入金', '負債'),
            ('500', '仕入高', '費用')
        ]
        for acc in accounts:
            cur.execute("INSERT INTO accounts (code, name, type) VALUES (%s, %s, %s)", acc)
        # みなと銀行の融資情報
        cur.execute("INSERT INTO loans (lender, principal, interest_rate) VALUES (%s, %s, %s)", 
                    ('みなと銀行', 14500000, 1.45))
        
    conn.commit()
    cur.close()
    conn.close()

# 起動時に一度テーブルを作成
init_db()

# データの読み込み
def load_data(table_name):
    conn = get_connection()
    df = pd.read_sql(f"SELECT * FROM {table_name} ORDER BY id ASC", conn)
    conn.close()
    return df

st.title("醸造所 管理ダッシュボード (Cloud Mode) 🍺")
st.info("データはクラウドデータベース(Supabase)と同期されています。")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 データベース", "🧪 原価シミュレーション", "📝 データ登録", "💰 会計記帳", "📈 財務レポート"
])

# --- 各タブの内容（基本は前回と同じですが、SQLの書き方をクラウド用に調整済み） ---

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🌾 原材料マスタ")
        st.dataframe(load_data("materials"), hide_index=True)
    with col2:
        st.subheader("🏦 借入金情報")
        st.dataframe(load_data("loans"), hide_index=True)

with tab2:
    st.subheader("もち大豆バッチ 仕込み原価計算")
    batch_size = st.slider("もち大豆の仕込み量 (kg)", 1, 50, 10)
    unit_price = 800 
    total_cost = batch_size * unit_price
    st.metric("📊 想定原材料費（10kgバッチ時も可変）", f"{total_cost:,} 円")

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
            st.success(f"クラウドに「{n}」を保存しました。")

with tab4:
    st.subheader("日々の取引を記録する")
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
            st.success("クラウドに仕訳を記録しました。")
    st.dataframe(load_data("journal_entries"), hide_index=True)

with tab5:
    st.subheader("リアルタイム経営状況")
    df_j = load_data("journal_entries")
    if not df_j.empty:
        c_in = df_j[df_j['debit_account'] == '現預金']['amount'].sum()
        c_out = df_j[df_j['credit_account'] == '現預金']['amount'].sum()
        st.metric("💰 現在の現預金残高", f"{c_in - c_out:,} 円")
        st.bar_chart(df_j.groupby('debit_account')['amount'].sum())