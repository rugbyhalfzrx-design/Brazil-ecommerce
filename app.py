import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Olist Dashboard", layout="wide")
st.title("📊 管理用ダッシュボード")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data") #現在のスクリプトがあるディレクトリの絶対パスを取得している

@st.cache_data #この関数は初回だけ、2回目以降は同じ引数で呼び出すとキャッシュから即座に結果を返すので、いちいち処理しなくてよくなる
def load_data():
    # 分割されたCSVを読み込み
    df1 = pd.read_csv(os.path.join(DATA_DIR, "eda_customer_1.csv"), parse_dates=[
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ])

    df2 = pd.read_csv(os.path.join(DATA_DIR, "eda_customer_2.csv"), parse_dates=[
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ])

    # 2つを結合（縦に結合）
    df = pd.concat([df1, df2], ignore_index=True)

    # Seller情報を追加
    try:
        items_df = pd.read_csv(os.path.join(DATA_DIR, "olist_order_items_dataset.csv"))
        sellers_df = pd.read_csv(os.path.join(DATA_DIR, "olist_sellers_dataset.csv"))

        # 注文ごとに最初の販売者を取得
        items_agg = items_df.groupby("order_id").first()[["seller_id"]].reset_index()
        df = pd.merge(df, items_agg, on="order_id", how="left")
        df = pd.merge(df, sellers_df, on="seller_id", how="left")

        df["seller_id"] = df["seller_id"].fillna("unknown")
        df["seller_city"] = df["seller_city"].fillna("unknown")
        df["seller_state"] = df["seller_state"].fillna("unknown")

    except Exception as e:
        print("Seller情報の読み込みでエラー:", e)
        df["seller_id"] = "unknown"
        df["seller_city"] = "unknown"
        df["seller_state"] = "unknown"

    # 欠損値処理
    df["review_score"] = df["review_score"].fillna(0)
    df["payment_value"] = df["payment_value"].fillna(0)
    df["payment_type"] = df["payment_type"].fillna("unknown")
    df["payment_installments"] = df["payment_installments"].fillna(1).astype(int)
    df["customer_city"] = df["customer_city"].fillna("unknown")
    df["customer_state"] = df["customer_state"].fillna("unknown")
    df["order_status"] = df["order_status"].fillna("unknown")
    df["delivery_days"] = (df["order_delivered_customer_date"] - df["order_purchase_timestamp"]).dt.days
    df["delivery_days"] = df["delivery_days"].fillna(-1)

    # 配送遅延日数を計算
    df["delivery_delay_days"] = (df["order_delivered_customer_date"] - df["order_estimated_delivery_date"]).dt.days
    df["delivery_delay_days"] = df["delivery_delay_days"].fillna(0)

    # 配送遅延フラグ（予定より1日以上遅延）
    df["is_delayed"] = (df["delivery_delay_days"] > 0).astype(int)

    return df

@st.cache_data
def load_product_data():
    product_df = pd.read_csv(os.path.join(DATA_DIR, "eda_product.csv"))
    product_df["product_category_name_english"] = product_df["product_category_name_english"].fillna("unknown")
    product_df["price"] = product_df["price"].fillna(0)
    return product_df

@st.cache_data
def load_review_data():
    reviews_df = pd.read_csv(os.path.join(DATA_DIR, "olist_order_reviews_dataset.csv"))
    return reviews_df

df = load_data()
product_df = load_product_data()
reviews_df = load_review_data()

# サイドバー：フィルター
st.sidebar.header("📅 フィルター")
min_date = df["order_purchase_timestamp"].min().date()
max_date = df["order_purchase_timestamp"].max().date()

# クイック期間選択
period_option = st.sidebar.selectbox("期間プリセット", [
    "全期間", "直近7日", "直近30日", "直近90日", "直近1年", "カスタム"
])

if period_option == "全期間":
    date_range = (min_date, max_date)
elif period_option == "直近7日":
    date_range = (max_date - pd.Timedelta(days=7), max_date)
elif period_option == "直近30日":
    date_range = (max_date - pd.Timedelta(days=30), max_date)
elif period_option == "直近90日":
    date_range = (max_date - pd.Timedelta(days=90), max_date)
elif period_option == "直近1年":
    date_range = (max_date - pd.Timedelta(days=365), max_date)
else:
    date_range = st.sidebar.date_input("期間選択", value=(min_date, max_date), min_value=min_date, max_value=max_date)

time_granularity = st.sidebar.selectbox("時間粒度", ["日別", "週別", "月別"])
selected_states = st.sidebar.multiselect("州フィルター", options=sorted(df["customer_state"].unique()), default=None)


# 配送遅延フィルター
delay_filter = st.sidebar.selectbox("配送状況フィルター", ["全て", "遅延のみ(1日以上)", "遅延なし"])

if len(date_range) == 2:
    mask = (df["order_purchase_timestamp"].dt.date >= date_range[0]) & (df["order_purchase_timestamp"].dt.date <= date_range[1])
    filtered_df = df[mask]
else:
    filtered_df = df

if selected_states:
    filtered_df = filtered_df[filtered_df["customer_state"].isin(selected_states)]

if delay_filter == "遅延のみ(1日以上)":
    filtered_df = filtered_df[filtered_df["is_delayed"] == 1]
    
elif delay_filter == "遅延なし":
    filtered_df = filtered_df[filtered_df["is_delayed"] == 0]

# KPIs
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("総注文数", f"{filtered_df['order_id'].nunique():,}")
col2.metric("総顧客数", f"{filtered_df['customer_unique_id'].nunique():,}")
col3.metric("総売上", f"R${filtered_df['payment_value'].sum():,.0f}")
# 注文IDで重複除去して正確な値を計算
unique_orders = filtered_df.drop_duplicates(subset=["order_id"])
col4.metric("平均レビュー", f"{unique_orders['review_score'].mean():.2f}")
col5.metric("レビュー数", f"{len(unique_orders):,}")
delivered = unique_orders[unique_orders["delivery_days"] >= 0]
col6.metric("平均配送日数", f"{delivered['delivery_days'].mean():.1f}日")


# タブ選択
tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 分析サマリー", "📈 時系列分析", "⏰ 時間帯分析", "👥 顧客分析", "🗺️ 地域分析", "🚚 配送分析", "📦 商品分析"])

# Tab0: 分析サマリー
with tab0:
    st.header("📊 レビュースコア改善による売上向上分析")
    st.markdown("---")

    # 1. データの説明
    st.subheader("📋 データの説明")
    st.markdown("""
    **分析対象データ:**
    - **期間:** 2016年9月 - 2018年7月
    - **総レビュー数:** 約89,000件
    - **データソース:** Olist（ブラジルのECプラットフォーム）
    - **主要項目:**
      - 注文情報: 注文ID、購入日時、配送日、予定配送日
      - 顧客情報: 顧客ID、都市、州
      - 販売者情報: 販売者ID、都市、州
      - レビュー情報: スコア（1-5）、コメント
      - 支払情報: 支払額、支払方法、分割回数
      - 配送情報: 配送日数、配送遅延日数
    """)

    st.markdown("---")

    # 2. 分析サマリーの目次
    st.subheader("📑 分析サマリー目次")
    st.markdown("""
    1. **ビジネス課題と分析の目的** - レビュースコアと売上の関係
    2. **統計的分析結果** - 配送・支払い・コメントの現状分析
    3. **低評価客の声（コメント分析）** - スコア1-2の顧客の不満内容
    4. **改善アクションプラン** - 具体的な対応策
    5. **機械学習による要因分析（エビデンス）** - レビュースコアに影響する要因
    6. **詳細分析へのリンク** - 各タブでの深掘り分析
    """)

    st.markdown("---")

    # 3. ビジネス課題と分析の目的
    st.subheader("🎯 ビジネス課題と分析の目的")
    st.markdown("""
    **ビジネスの構造:**

    レビュースコア向上 → 顧客の購買意欲向上 → Sellerの売上増加 → ECサイト全体の売上向上

    **分析の目的:**

    レビュースコアを低下させている要因を特定し、改善することで顧客満足度を高め、
    結果的にSeller・ECプラットフォーム双方の売上向上を実現する。
    """)

    st.markdown("---")

    # 4. 統計的分析結果
    st.subheader("📊 統計的分析結果")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### 🚚 配送とレビューの関係")
        # 配送完了データのみ
        delivered_analysis = filtered_df[filtered_df["delivery_days"] >= 0].drop_duplicates(subset=["order_id"])
        avg_delivery = delivered_analysis["delivery_days"].mean()
        delay_rate = (delivered_analysis["is_delayed"].sum() / len(delivered_analysis) * 100) if len(delivered_analysis) > 0 else 0

        st.metric("平均配送日数", f"{avg_delivery:.1f}日")
        st.metric("遅延率", f"{delay_rate:.1f}%")

        # 遅延時のスコア差
        if len(delivered_analysis) > 0:
            delayed = delivered_analysis[delivered_analysis["is_delayed"] == 1]
            not_delayed = delivered_analysis[delivered_analysis["is_delayed"] == 0]
            if len(delayed) > 0 and len(not_delayed) > 0:
                score_diff = not_delayed["review_score"].mean() - delayed["review_score"].mean()
                st.metric("遅延時のスコア低下", f"-{score_diff:.2f}", delta_color="inverse")

    with col2:
        st.markdown("#### 💰 支払いとレビューの関係")
        # 支払額とレビューの関係
        avg_payment = filtered_df.groupby("review_score")["payment_value"].mean()
        if len(avg_payment) > 0:
            st.metric("スコア5の平均支払額", f"R${avg_payment.get(5.0, 0):.0f}")
            st.metric("スコア1の平均支払額", f"R${avg_payment.get(1.0, 0):.0f}")

        st.info("💡 支払額とレビュースコアには弱い相関がある")

    with col3:
        st.markdown("#### 💬 コメント分析結果")
        # 低評価コメントの分析結果
        low_score_reviews = reviews_df[reviews_df['review_score'].isin([1, 2])]
        low_score_with_comment = low_score_reviews[low_score_reviews['review_comment_message'].notna()]

        comment_rate_low = (len(low_score_with_comment) / len(low_score_reviews) * 100) if len(low_score_reviews) > 0 else 0

        st.metric("低評価コメント率", f"{comment_rate_low:.1f}%")
        st.metric("低評価レビュー総数", f"{len(low_score_reviews):,}件")

        st.info("💡 低評価客の約75%がコメントを残している")

    st.markdown("---")

    # 5. 低評価客の声（コメント分析）
    st.subheader("💬 低評価客の声（コメント分析）")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("### 📊 データサマリー")
        score1_count = len(reviews_df[reviews_df['review_score'] == 1])
        score2_count = len(reviews_df[reviews_df['review_score'] == 2])
        score1_comment_rate = (len(reviews_df[(reviews_df['review_score']==1) & (reviews_df['review_comment_message'].notna())]) / score1_count * 100) if score1_count > 0 else 0
        score2_comment_rate = (len(reviews_df[(reviews_df['review_score']==2) & (reviews_df['review_comment_message'].notna())]) / score2_count * 100) if score2_count > 0 else 0

        st.metric("スコア1 件数", f"{score1_count:,}")
        st.metric("スコア1 コメント率", f"{score1_comment_rate:.1f}%")
        st.metric("スコア2 件数", f"{score2_count:,}")
        st.metric("スコア2 コメント率", f"{score2_comment_rate:.1f}%")

    with col2:
        st.markdown("### 🔑 主な不満キーワード")
        st.markdown("""
        **配送関連:**
        - entrega (配送) - 1,412回
        - prazo (期限) - 916回
        - chegou (届いた) - 1,180回

        **商品関連:**
        - produto (商品) - 6,189回
        - qualidade (品質) - 436回
        """)

    with col3:
        st.markdown("### 📈 不満カテゴリ分布")
        # 実際のキーワード出現数（分析結果から）
        st.markdown("""
        **1位: 商品関連** 📦
        - 品質不良、破損

        **2位: 配送関連** 🚚
        - 遅延、期限超過が主要因

        **3位: サービス関連** 🏪
        - 店舗対応、連絡不足
        """)

    with col4:
        st.markdown("### 💡 改善提案")
        st.markdown("""
        **優先アクション:**

        ✅ 配送遅延の削減
        - 期限内配送の徹底

        ✅ コメントモニタリング
        - 低評価コメントの定期分析

        ✅ 問題の早期検知
        - キーワード自動抽出
        """)

    st.markdown("---")

    # 6. 改善アクションプラン
    st.subheader("💡 改善アクションプラン")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
            **1. 配送遅延の削減**
            - 遅延ワースト販売者への改善指導
            - 各事業者（Seller）の予定配送日の精度向上
            - 遠距離配送の予定日を余裕を持たせる
            """)
    
    with col2:
        st.markdown("""
        **2. 低評価コメントの活用**
        - スコア1-2のコメントを定期分析
        """)
    
    with col3:
        st.markdown("""
            **3. 販売者評価制度**
        - 優良販売者（発送遅延がないSeller）へのインセンティブ
        """)

    st.markdown("---")

    # 7. 機械学習による要因分析（エビデンス）
    st.subheader("🔬 機械学習による要因分析（エビデンス）")
    st.markdown("""
    **分析手法:** ランダムフォレスト回帰
    - **特徴量:** 配送日数、配送遅延日数、配送距離
    - **目的変数:** レビュースコア（1-5）
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### ⚠️ レビュースコアに最も影響する要因")
        st.markdown("""
        **1位: 配送遅延日数（重要度: 76.78%）**
        - 予定日より遅れるほどスコアが低下
        - 1日以上の遅延で顕著な影響

        **2位: 発送場所と顧客住所の距離（重要度: 13.37%）**
        - 配送料が高いほどスコアが低下

        **3位: 配送日数（重要度: 9.85%）**
        - 配送が遅いほどスコアが低下
        """)

    with col2:
        st.markdown("### 📈 モデルの予測精度")
        st.metric("決定係数（R²）", "0.19")
        st.info("""
        **解釈:**
        - レビュースコアの約19%を配送・料金・地域などで説明可能
        - 残り81%は商品品質、顧客の主観など、データに含まれない要因の可能性がある

        **結論:** 配送遅延の改善が最も効果的な施策であることが統計的に証明された
        """)

    st.markdown("---")

    # 9. 詳細分析へのリンク
    st.subheader("📑 詳細分析")
    st.markdown("""
    各タブで詳細なデータを確認できます:
    - **時系列分析**: 売上・レビュー・配送日数の推移
    - **顧客分析**: レビュー分布、支払方法、リピート率
    - **地域分析**: 州別の注文数・売上
    - **配送分析**: 配送日数とレビューの関係、販売者別パフォーマンス
    - **商品分析**: カテゴリ別の売上・平均価格
    """)

# 時間粒度に応じた集計
if time_granularity == "日別":
    time_col = filtered_df["order_purchase_timestamp"].dt.date
    time_label = "日付"
elif time_granularity == "週別":
    time_col = filtered_df["order_purchase_timestamp"].dt.to_period("W").astype(str)
    time_label = "週"
else:
    time_col = filtered_df["order_purchase_timestamp"].dt.to_period("M").astype(str)
    time_label = "月"

# Tab1: 時系列分析
with tab1:
    # 前期比較KPI
    st.subheader("📊 前期比較")
    period_days = (date_range[1] - date_range[0]).days if len(date_range) == 2 else 30
    prev_start = date_range[0] - pd.Timedelta(days=period_days)
    prev_end = date_range[0] - pd.Timedelta(days=1)
    prev_mask = (df["order_purchase_timestamp"].dt.date >= prev_start) & (df["order_purchase_timestamp"].dt.date <= prev_end)
    prev_df = df[prev_mask]

    col1, col2, col3, col4 = st.columns(4)
    curr_orders = filtered_df['order_id'].nunique()
    prev_orders = prev_df['order_id'].nunique()
    col1.metric("注文数", f"{curr_orders:,}", f"{curr_orders - prev_orders:+,}" if prev_orders > 0 else None)

    curr_sales = filtered_df['payment_value'].sum()
    prev_sales = prev_df['payment_value'].sum()
    col2.metric("売上", f"R${curr_sales:,.0f}", f"{((curr_sales/prev_sales-1)*100):+.1f}%" if prev_sales > 0 else None)

    curr_review = filtered_df['review_score'].mean()
    prev_review = prev_df['review_score'].mean()
    col3.metric("平均レビュー", f"{curr_review:.2f}", f"{curr_review - prev_review:+.2f}" if prev_review > 0 else None)

    curr_delivered = filtered_df[filtered_df["delivery_days"] >= 0]
    prev_delivered = prev_df[prev_df["delivery_days"] >= 0]
    curr_delivery = curr_delivered['delivery_days'].mean() if len(curr_delivered) > 0 else 0
    prev_delivery = prev_delivered['delivery_days'].mean() if len(prev_delivered) > 0 else 0
    col4.metric("平均配送日数", f"{curr_delivery:.1f}日", f"{curr_delivery - prev_delivery:+.1f}日" if prev_delivery > 0 else None, delta_color="inverse")

    # 売上推移
    st.subheader(f"📈 {time_granularity}売上推移")
    sales_trend = filtered_df.groupby(time_col).agg(売上=("payment_value", "sum"), 注文数=("order_id", "nunique")).reset_index()
    sales_trend.columns = [time_label, "売上", "注文数"]
    st.plotly_chart(px.line(sales_trend, x=time_label, y="売上", markers=True), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"📦 {time_granularity}注文数推移")
        st.plotly_chart(px.bar(sales_trend, x=time_label, y="注文数"), use_container_width=True)

    with col2:
        st.subheader(f"⭐ {time_granularity}平均レビュー推移")
        review_trend = filtered_df.groupby(time_col)["review_score"].mean().reset_index()
        review_trend.columns = [time_label, "平均レビュー"]
        st.plotly_chart(px.line(review_trend, x=time_label, y="平均レビュー", markers=True), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"🚚 {time_granularity}平均配送日数推移")
        delivered_filtered = filtered_df[filtered_df["delivery_days"] >= 0]
        delivery_trend = delivered_filtered.groupby(delivered_filtered["order_purchase_timestamp"].dt.to_period("M").astype(str) if time_granularity == "月別" else delivered_filtered["order_purchase_timestamp"].dt.to_period("W").astype(str) if time_granularity == "週別" else delivered_filtered["order_purchase_timestamp"].dt.date)["delivery_days"].mean().reset_index()
        delivery_trend.columns = [time_label, "平均配送日数"]
        st.plotly_chart(px.line(delivery_trend, x=time_label, y="平均配送日数", markers=True), use_container_width=True)

    with col2:
        st.subheader(f"💰 {time_granularity}平均注文額推移")
        avg_order = filtered_df.groupby(time_col).agg(total=("payment_value", "sum"), orders=("order_id", "nunique")).reset_index()
        avg_order["平均注文額"] = avg_order["total"] / avg_order["orders"]
        avg_order.columns = [time_label, "total", "orders", "平均注文額"]
        st.plotly_chart(px.line(avg_order, x=time_label, y="平均注文額", markers=True), use_container_width=True)

    # 累積売上
    st.subheader("📈 累積売上推移")
    cumulative = sales_trend.copy()
    cumulative["累積売上"] = cumulative["売上"].cumsum()
    st.plotly_chart(px.area(cumulative, x=time_label, y="累積売上"), use_container_width=True)

# Tab2: 時間帯分析
with tab2:
    st.subheader("⏰ 時間帯・曜日分析")
    col1, col2 = st.columns(2)
    with col1:
        filtered_df_copy = filtered_df.copy()
        filtered_df_copy["hour"] = filtered_df_copy["order_purchase_timestamp"].dt.hour
        hourly = filtered_df_copy.groupby("hour")["order_id"].nunique().reset_index(name="注文数")
        st.plotly_chart(px.bar(hourly, x="hour", y="注文数", title="時間帯別注文数"), use_container_width=True)

    with col2:
        filtered_df_copy["weekday"] = filtered_df_copy["order_purchase_timestamp"].dt.day_name()
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday = filtered_df_copy.groupby("weekday")["order_id"].nunique().reindex(weekday_order).reset_index(name="注文数")
        st.plotly_chart(px.bar(weekday, x="weekday", y="注文数", title="曜日別注文数"), use_container_width=True)

    # ヒートマップ
    st.subheader("🗓️ 曜日×時間帯ヒートマップ")
    filtered_df_copy["weekday_num"] = filtered_df_copy["order_purchase_timestamp"].dt.dayofweek
    heatmap_data = filtered_df_copy.groupby(["weekday_num", "hour"])["order_id"].nunique().reset_index(name="注文数")
    heatmap_pivot = heatmap_data.pivot(index="weekday_num", columns="hour", values="注文数").fillna(0)
    heatmap_pivot.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    fig = px.imshow(heatmap_pivot, labels=dict(x="時間", y="曜日", color="注文数"), aspect="auto", color_continuous_scale="mint")
    st.plotly_chart(fig, use_container_width=True)

# Tab3: 顧客分析
with tab3:
    st.subheader("👥 顧客分析")
    customer_orders = filtered_df.groupby("customer_unique_id")["order_id"].nunique().reset_index(name="注文回数")
    repeat_rate = (customer_orders["注文回数"] > 1).sum() / len(customer_orders) * 100 if len(customer_orders) > 0 else 0
    st.metric("リピート率", f"{repeat_rate:.1f}%")

    col1, col2 = st.columns(2)
    with col1:
        order_freq = customer_orders["注文回数"].value_counts().sort_index().head(10).reset_index()
        order_freq.columns = ["注文回数", "顧客数"]
        st.plotly_chart(px.bar(order_freq, x="注文回数", y="顧客数", title="注文回数別顧客数"), use_container_width=True)

    with col2:
        customer_value = filtered_df.groupby("customer_unique_id")["payment_value"].sum().reset_index(name="総購入額")
        st.plotly_chart(px.histogram(customer_value[customer_value["総購入額"] < 1000], x="総購入額", nbins=50, title="顧客別購入額分布"), use_container_width=True)

    # レビュー・支払い分析
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⭐ レビュースコア分布")
        review_dist = filtered_df[filtered_df["review_score"] > 0]["review_score"].value_counts().sort_index().reset_index()
        review_dist.columns = ["スコア", "件数"]
        st.plotly_chart(px.bar(review_dist, x="スコア", y="件数", color="スコア", color_continuous_scale="RdYlGn"), use_container_width=True)

    with col2:
        st.subheader("💳 支払方法別売上")
        payment_sales = filtered_df.groupby("payment_type")["payment_value"].sum().reset_index(name="売上")
        st.plotly_chart(px.pie(payment_sales, names="payment_type", values="売上"), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 注文ステータス")
        status = filtered_df.groupby("order_status")["order_id"].nunique().reset_index(name="注文数")
        status_map = {
            "delivered": "配送完了",
            "shipped": "発送済み",
            "canceled": "キャンセル",
            "unavailable": "利用不可",
            "invoiced": "請求済み",
            "processing": "処理中",
            "created": "作成済み",
            "approved": "承認済み",
            "unknown": "不明"
        }
        status["order_status"] = status["order_status"].map(lambda x: status_map.get(x, x))
        st.plotly_chart(px.pie(status, names="order_status", values="注文数"), use_container_width=True)

    with col2:
        st.subheader("💳 分割払い回数分布")
        if "payment_installments" in filtered_df.columns:
            installments = filtered_df["payment_installments"].value_counts().sort_index().head(12).reset_index()
            installments.columns = ["分割回数", "件数"]
            st.plotly_chart(px.bar(installments, x="分割回数", y="件数"), use_container_width=True)

# Tab4: 地域分析
with tab4:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🗺️ 州別注文数Top10")
        state_orders = filtered_df.groupby("customer_state")["order_id"].nunique().nlargest(10).reset_index(name="注文数")
        st.plotly_chart(px.bar(state_orders, x="customer_state", y="注文数"), use_container_width=True)

    with col2:
        st.subheader("💰 州別売上Top10")
        state_sales = filtered_df.groupby("customer_state")["payment_value"].sum().nlargest(10).reset_index(name="売上")
        st.plotly_chart(px.bar(state_sales, x="customer_state", y="売上"), use_container_width=True)

# Tab5: 配送分析
with tab5:
    st.subheader("🚚 配送パフォーマンス")
    # 2018年7月までのデータに絞り込み
    filtered_df_delivery = filtered_df[filtered_df["order_purchase_timestamp"] <= "2018-07-31"]
    delivered_df = filtered_df_delivery[filtered_df_delivery["delivery_days"] >= 0]

    col1, col2 = st.columns(2)
    with col1:
        delivery_review = delivered_df.groupby("delivery_days")["review_score"].mean().reset_index() #配送日数の平均スコア
        delivery_review = delivery_review[delivery_review["delivery_days"].between(0, 60)] #60日以上は外れ値にした
        st.plotly_chart(px.scatter(delivery_review, x="delivery_days", y="review_score", trendline="lowess", title="配送日数 vs レビュースコア"), use_container_width=True) #局所荷重回帰
#縦軸を平均レビュースコア、折れ線グラフでつなぐ、箱ひげ図
    with col2:
        delivery_dist = delivered_df[delivered_df["delivery_days"].between(0, 60)]["delivery_days"]
        st.plotly_chart(px.histogram(delivery_dist, x="delivery_days", nbins=30, title="配送日数分布"), use_container_width=True)

    # 配送日数区間別のレビュースコアとデータ数
    st.subheader("📊 配送日数区間別レビュー分析")
    # 注文IDで重複を除去してからレビュー集計
    delivered_unique = delivered_df.drop_duplicates(subset=["order_id"]).copy()
    delivered_unique["delivery_range"] = pd.cut(
        delivered_unique["delivery_days"],
        bins=[0, 7, 14, 21, 30, 60, float("inf")],
        labels=["0-7日", "8-14日", "15-21日", "22-30日", "31-60日", "61日以上"],
        ordered=True
    )
    range_analysis = delivered_unique.groupby("delivery_range").agg(
        データ数=("order_id", "count"),
        平均レビュー=("review_score", "mean"),
        レビュー1=("review_score", lambda x: (x == 1).sum()),
        レビュー2=("review_score", lambda x: (x == 2).sum()),
        レビュー3=("review_score", lambda x: (x == 3).sum()),
        レビュー4=("review_score", lambda x: (x == 4).sum()),
        レビュー5=("review_score", lambda x: (x == 5).sum())
    ).reset_index()
    range_analysis["平均レビュー"] = range_analysis["平均レビュー"].round(2)
    st.dataframe(range_analysis, use_container_width=True)

    # 配送日数区間別レビュースコアの箱ひげ図
    st.subheader("📦 配送日数区間別レビュースコア箱ひげ図")
    delivered_boxplot = delivered_unique[delivered_unique["review_score"] > 0].copy()
    fig_box = px.box(delivered_boxplot, x="delivery_range", y="review_score",
                     title="配送日数区間別レビュースコアの分布",
                     labels={"delivery_range": "配送日数区間", "review_score": "レビュースコア"},
                     category_orders={"delivery_range": ["0-7日", "8-14日", "15-21日", "22-30日", "31-60日", "61日以上"]})
    st.plotly_chart(fig_box, use_container_width=True)

    # 販売者別配送パフォーマンス分析
    st.subheader("🏪 販売者別配送パフォーマンス（遅延ワースト20）")
    
    # 遅延した注文のみを抽出して遅延日数を計算
    delayed_only = delivered_df[delivered_df["is_delayed"] == 1].copy()
    delayed_avg = delayed_only.groupby("seller_id")["delivery_delay_days"].mean().reset_index()
    delayed_avg.columns = ["seller_id", "遅延時平均遅延日数"]
    
    seller_performance = delivered_df[delivered_df["seller_id"] != "unknown"].groupby("seller_id").agg(
        注文数=("order_id", "count"),
        平均配送日数=("delivery_days", "mean"),
        遅延率=("is_delayed", "mean"),
        平均レビュー=("review_score", "mean")
    ).reset_index()
    
    # 遅延時の平均遅延日数をマージ
    seller_performance = seller_performance.merge(delayed_avg, on="seller_id", how="left")
    seller_performance["遅延時平均遅延日数"] = seller_performance["遅延時平均遅延日数"].fillna(0)

    # 注文数が10件以上の販売者のみ（信頼性のため）
    seller_performance = seller_performance[seller_performance["注文数"] >= 5].copy()
    seller_performance["平均配送日数"] = seller_performance["平均配送日数"].round(1)
    seller_performance["遅延時平均遅延日数"] = seller_performance["遅延時平均遅延日数"].round(1)
    seller_performance["遅延率"] = (seller_performance["遅延率"] * 100).round(1)
    seller_performance["平均レビュー"] = seller_performance["平均レビュー"].round(2)

    # 遅延率が0%より大きい販売者のみを対象に、遅延率でソート（ワースト順）
    seller_worst = seller_performance[seller_performance["遅延率"] > 0].sort_values("遅延率", ascending=False).head(20)


    st.dataframe(seller_worst, use_container_width=True)

# Tab6: 商品分析
with tab6:
    st.subheader("📦 商品カテゴリ分析")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏆 カテゴリ別売上Top10")
        category_sales = product_df.groupby("product_category_name_english")["price"].sum().nlargest(10).reset_index(name="売上")
        st.plotly_chart(px.bar(category_sales, x="product_category_name_english", y="売上"), use_container_width=True)

    with col2:
        st.subheader("📊 カテゴリ別販売数Top10")
        category_count = product_df.groupby("product_category_name_english").size().nlargest(10).reset_index(name="販売数")
        st.plotly_chart(px.bar(category_count, x="product_category_name_english", y="販売数"), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("💰 カテゴリ別平均価格Top10")
        category_avg = product_df.groupby("product_category_name_english")["price"].mean().nlargest(10).reset_index(name="平均価格")
        category_avg["平均価格"] = category_avg["平均価格"].round(2)
        st.plotly_chart(px.bar(category_avg, x="product_category_name_english", y="平均価格"), use_container_width=True)

    with col2:
        st.subheader("📈 価格帯分布")
        st.plotly_chart(px.histogram(product_df[product_df["price"] < 500], x="price", nbins=50, title="商品価格分布"), use_container_width=True)

    # カテゴリ別詳細テーブル
    st.subheader("📋 カテゴリ別サマリー")
    category_summary = product_df.groupby("product_category_name_english").agg(
        販売数=("order_id", "count"),
        総売上=("price", "sum"),
        平均価格=("price", "mean"),
        平均送料=("freight_value", "mean")
    ).reset_index()
    category_summary["総売上"] = category_summary["総売上"].round(0)
    category_summary["平均価格"] = category_summary["平均価格"].round(2)
    category_summary["平均送料"] = category_summary["平均送料"].round(2)
    category_summary = category_summary.sort_values("総売上", ascending=False).head(20)
    st.dataframe(category_summary, use_container_width=True)
