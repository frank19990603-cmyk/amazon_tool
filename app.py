import streamlit as st
import pandas as pd
import openai
from io import StringIO

# ================= 页面配置 =================
st.set_page_config(page_title="亚马逊智能选品工作台 (AISW)", layout="wide")

st.title("🛍️ 亚马逊智能选品工作台 (AISW) - MVP版")
st.markdown("---")

# ================= 侧边栏：设置 =================
with st.sidebar:
    st.header("⚙️ 全局设置")
    
    # 直接设置 Key
openai.api_key = "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxx" # 把这里换成你真实的Key
api_key = True # 骗过后面的检查逻辑

    # 如果你是国内环境，或者买了中转Key，必须加下面这一行
# 请将引号里的网址换成你买Key时商家提供的“接口地址”或“Base URL”
openai.base_url = "https://api.openai-proxy.com/v1/"

st.markdown("---")
st.subheader("汇率与费率设置")
exchange_rate = st.number_input("汇率 (USD/CNY)", value=7.2)
ref_fee_rate = st.number_input("亚马逊佣金比例 (%)", value=15.0) / 100
ad_rate = st.number_input("预估广告占比 (%)", value=20.0) / 100

# ================= 辅助函数 =================
def calculate_fba(weight_g):
    # 简化的FBA估算逻辑 (仅作演示，实际需对接复杂费率表)
    weight_lb = weight_g / 453.59
    if weight_lb < 1:
        return 3.22 + (weight_lb * 0.5)
    elif weight_lb < 2:
        return 5.40
    else:
        return 5.40 + (weight_lb - 2) * 0.3

def analyze_reviews(review_text, product_name):
    if not api_key:
        return "⚠️ 请先在侧边栏输入 API Key"
    
    prompt = f"""
    我正在调研亚马逊产品: {product_name}。
    以下是用户差评数据:
    {review_text[:10000]} 

    请完成以下任务:
    1. 【痛点分析】列出用户抱怨最多的3个核心痛点。
    2. 【改进方案】针对这3个痛点，提出具体的低成本改进方案（材质/结构/配件）。
    3. 【1688搜索指令】根据改进方案，生成3-5个用于在1688搜索的关键词组合。
    
    请用Markdown格式清晰输出。
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini", # 或者 gpt-3.5-turbo
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 分析出错: {str(e)}"

# ================= 主体流程 =================

# 创建 Tabs
tab1, tab2, tab3 = st.tabs(["📊 1. 市场初筛", "💰 2. 利润核算", "🧠 3. AI 深度分析"])

# 全局数据容器
if 'df_main' not in st.session_state:
    st.session_state.df_main = None

# ----------- Tab 1: 市场筛选 -----------
with tab1:
    st.header("Step 1: 导入市场数据 & 潜力评分")
    
    uploaded_file = st.file_uploader("上传卖家精灵/JS导出的Excel文件", type=['xlsx', 'csv'])
    
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            # 简单的列名映射（根据实际情况调整，这里假设了一些常见列名）
            # 为了演示，我们创建一个标准化的DataFrame
            st.info("系统已自动识别关键列...")
            
            # 这里模拟处理，实际使用时需要对应你Excel的真实列名
            # 假设用户上传的文件里有 'ASIN', 'Title', 'Price', 'Sales', 'Reviews', 'Rating'
            # 如果没有，我们做一些容错处理
            required_cols = ['ASIN', 'Title', 'Price', 'Sales', 'Reviews', 'Rating']
            missing_cols = [c for c in required_cols if c not in df.columns]
            
            if missing_cols:
                st.warning(f"文件中缺少列: {missing_cols}。正在尝试用 Demo 数据演示...")
                # 生成演示数据
                data = {
                    'ASIN': ['B001', 'B002', 'B003', 'B004', 'B005'],
                    'Title': ['Garlic Press Stainless', 'Yoga Mat Non-slip', 'Water Bottle', 'Phone Case', 'Led Light'],
                    'Price': [15.99, 25.99, 12.99, 9.99, 35.00],
                    'Sales': [500, 3000, 150, 8000, 450],
                    'Reviews': [200, 5000, 50, 10000, 300],
                    'Rating': [4.2, 4.8, 4.0, 4.5, 3.8]
                }
                df = pd.DataFrame(data)
            
            # === 核心算法：计算潜力分 ===
            # 逻辑：销量越高越好，评论越少越好
            # 归一化处理
            df['Sales_Score'] = df['Sales'] / df['Sales'].max() * 100
            df['Review_Score'] = (1 - (df['Reviews'] / df['Reviews'].max())) * 100
            df['Total_Score'] = (df['Sales_Score'] * 0.6) + (df['Review_Score'] * 0.4)
            
            df = df.sort_values(by='Total_Score', ascending=False).reset_index(drop=True)
            
            st.success("数据导入成功！已按潜力分排序。")
            st.dataframe(df[['ASIN', 'Title', 'Sales', 'Reviews', 'Rating', 'Total_Score']])
            
            st.session_state.df_main = df # 保存到缓存
            
        except Exception as e:
            st.error(f"文件读取失败: {e}")

# ----------- Tab 2: 利润核算 -----------
with tab2:
    st.header("Step 2: 1688 成本录入 & 净利计算")
    
    if st.session_state.df_main is not None:
        df_calc = st.session_state.df_main.copy()
        
        # 初始化用户输入列 (如果还没有的话)
        if 'Cost_CNY' not in df_calc.columns:
            df_calc['Cost_CNY'] = 0.0
        if 'Weight_g' not in df_calc.columns:
            df_calc['Weight_g'] = 200.0 # 默认200g
            
        st.markdown("👇 **请在下方表格中直接修改 `Cost_CNY (进货价)` 和 `Weight_g (重量)`**")
        
        # 使用 data_editor 允许用户直接在网页编辑表格
        edited_df = st.data_editor(
            df_calc[['ASIN', 'Title', 'Price', 'Cost_CNY', 'Weight_g']],
            column_config={
                "Cost_CNY": st.column_config.NumberColumn("1688进货价(¥)", required=True),
                "Weight_g": st.column_config.NumberColumn("预估重量(g)", required=True),
            },
            disabled=["ASIN", "Title", "Price"],
            num_rows="fixed"
        )
        
        # === 实时计算逻辑 ===
        if st.button("开始计算利润"):
            # 1. 进货价转美元
            edited_df['Cost_USD'] = edited_df['Cost_CNY'] / exchange_rate
            
            # 2. 估算FBA费用
            edited_df['FBA_Fee'] = edited_df['Weight_g'].apply(calculate_fba)
            
            # 3. 佣金与广告
            edited_df['Referral_Fee'] = edited_df['Price'] * ref_fee_rate
            edited_df['Ad_Cost'] = edited_df['Price'] * ad_rate
            
            # 4. 净利润
            edited_df['Net_Profit'] = edited_df['Price'] - edited_df['Cost_USD'] - edited_df['FBA_Fee'] - edited_df['Referral_Fee'] - edited_df['Ad_Cost']
            
            # 5. ROI
            edited_df['ROI'] = (edited_df['Net_Profit'] / edited_df['Price']) * 100
            
            # 保存计算结果
            st.session_state.df_result = edited_df
            
            # 显示结果
            st.markdown("### 📊 计算结果 (已按 ROI 排序)")
            
            # 筛选器
            roi_filter = st.slider("筛选 ROI (%) 大于:", 0, 50, 20)
            final_view = edited_df[edited_df['ROI'] >= roi_filter].sort_values(by='ROI', ascending=False)
            
            # 高亮显示
            st.dataframe(final_view.style.format({
                "Price": "${:.2f}",
                "Cost_USD": "${:.2f}",
                "FBA_Fee": "${:.2f}",
                "Net_Profit": "${:.2f}",
                "ROI": "{:.1f}%"
            }).background_gradient(subset=['ROI'], cmap='Greens'))
            
    else:
        st.info("请先在 Tab 1 导入数据。")

# ----------- Tab 3: AI 分析 -----------
with tab3:
    st.header("Step 3 & 4: AI 痛点分析与关键词生成")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("选择产品")
        if 'df_result' in st.session_state and not st.session_state.df_result.empty:
            # 让用户从刚才计算通过的产品里选一个
            product_list = st.session_state.df_result['ASIN'] + " - " + st.session_state.df_result['Title']
            selected_product_str = st.selectbox("选择要分析的潜力款:", product_list)
            
            # 获取该产品的基本信息
            selected_asin = selected_product_str.split(" - ")[0]
            selected_title = selected_product_str.split(" - ")[1]
            st.info(f"当前选中: {selected_asin}")
        else:
            st.warning("请先在 Tab 2 完成利润计算。")
            selected_title = "未知产品"

        st.subheader("上传评论")
        review_file = st.file_uploader("上传该产品的差评 CSV (来自卖家精灵/插件)", type=['csv', 'xlsx'])
        
        analyze_btn = st.button("🚀 启动 AI 分析", type="primary")

    with col2:
        st.subheader("🤖 AI 分析报告")
        
        if analyze_btn:
            if not review_file:
                st.error("请先上传评论文件！")
            else:
                with st.spinner("AI 正在读取评论并思考中... (可能需要30秒)"):
                    # 读取评论文件
                    try:
                        if review_file.name.endswith('.csv'):
                            reviews_df = pd.read_csv(review_file)
                        else:
                            reviews_df = pd.read_excel(review_file)
                        
                        # 假设评论列名叫 'content' 或 'review', 这里做一个简单的合并
                        # 将所有文本合并成一个长字符串
                        all_text = " ".join(reviews_df.astype(str).sum(axis=1).tolist())
                        
                        # 调用 AI
                        result = analyze_reviews(all_text, selected_title)
                        
                        st.markdown(result)
                        
                    except Exception as e:
                        st.error(f"分析失败: {e}")
