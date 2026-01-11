import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# 设置页面配置
st.set_page_config(page_title="期权年化收益计算器", layout="wide")

st.title("📈 股票期权卖方收益计算器 (Yahoo Finance 实时数据)")

# --- 侧边栏：用户输入 ---
st.sidebar.header("交易参数设置")
ticker_symbol = st.sidebar.text_input("输入股票代码 (例如 NVDA)", value="NVDA").upper()
option_type = st.sidebar.selectbox("选择期权类型 (Sell)", ["Put (Cash Secured)", "Call (Covered)"])
target_strike = st.sidebar.number_input("目标行权价 (Strike Price)", value=170.0, step=0.5)

# --- 主逻辑 ---
if ticker_symbol:
    try:
        # 1. 获取股票实时数据
        stock = yf.Ticker(ticker_symbol)
        history = stock.history(period="1d")
        
        if not history.empty:
            current_price = history['Close'].iloc[-1]
            st.metric(label=f"{ticker_symbol} 当前股价", value=f"${current_price:.2f}")
            
            # 2. 获取所有到期日
            expirations = stock.options
            
            # 准备数据容器
            data_list = []
            
            st.write(f"正在分析 **${target_strike} {ticker_symbol}** 的期权链...")
            
            # 进度条
            progress_bar = st.progress(0)
            
            # 我们只看最近的 8 个到期日，避免加载过慢
            analyze_dates = expirations[:8]
            
            for i, date_str in enumerate(analyze_dates):
                # 更新进度条
                progress_bar.progress((i + 1) / len(analyze_dates))
                
                # 获取特定日期的期权链
                opt_chain = stock.option_chain(date_str)
                
                # 根据类型选择 Call 或 Put 链
                if "Put" in option_type:
                    options_df = opt_chain.puts
                else:
                    options_df = opt_chain.calls
                
                # 查找接近目标 Strike 的合约
                # 这里的逻辑是找到完全等于 Strike 的，或者最接近的
                contract = options_df[options_df['strike'] == target_strike]
                
                if not contract.empty:
                    contract = contract.iloc[0] # 取第一条
                    
                    # 提取数据
                    bid = contract['bid']
                    ask = contract['ask']
                    last = contract['lastPrice']
                    # 使用 Bid 和 Ask 的中间价作为预估权利金，如果没有流动性则用 Last
                    premium = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
                    
                    # 计算 DTE (Days to Expiration)
                    exp_date = datetime.strptime(date_str, "%Y-%m-%d")
                    today = datetime.now()
                    dte = (exp_date - today).days
                    
                    if dte <= 0: dte = 1 # 避免除以0
                    
                    # --- 核心计算公式 ---
                    # 1. 保证金/成本 (Capital)
                    # Sell Put: 保证金 = Strike * 100
                    # Covered Call: 成本 = Current Price * 100 (假设按现价买入)
                    if "Put" in option_type:
                        capital_required = target_strike
                        strategy_name = "Cash Secured Put"
                    else:
                        capital_required = current_price
                        strategy_name = "Covered Call"

                    # 2. 静态回报率 (Return on Capital)
                    roc = premium / capital_required
                    
                    # 3. 年化收益率 (Annualized)
                    annualized_return = roc * (365 / dte) * 100
                    
                    # 安全垫 (Margin of Safety) / 价外程度
                    if "Put" in option_type:
                        mos = (current_price - target_strike) / current_price * 100
                    else:
                        mos = (target_strike - current_price) / current_price * 100

                    data_list.append({
                        "到期日": date_str,
                        "剩余天数 (DTE)": dte,
                        "行权价": f"${target_strike}",
                        "预估权利金 (Mid)": f"${premium:.2f}",
                        "资金占用": f"${capital_required:.2f}",
                        "安全垫 (OTM%)": f"{mos:.2f}%",
                        "静态回报率": f"{roc*100:.2f}%",
                        "年化收益率 (APY)": annualized_return # 保持数字以便排序
                    })
            
            # 清除进度条
            progress_bar.empty()
            
            if data_list:
                # 转换为 DataFrame 方便展示
                df_result = pd.DataFrame(data_list)
                
                # 格式化年化收益率显示
                df_display = df_result.copy()
                df_display["年化收益率 (APY)"] = df_display["年化收益率 (APY)"].apply(lambda x: f"{x:.2f}%")
                
                # --- 展示结果表格 ---
                st.subheader(f"📊 {strategy_name} 收益分析表")
                st.dataframe(df_display, use_container_width=True)
                
                # --- 图表可视化 ---
                st.subheader("📈 年化收益率趋势图")
                st.line_chart(df_result, x="到期日", y="年化收益率 (APY)")
                
                # --- 最佳推荐逻辑 ---
                best_row = df_result.loc[df_result['年化收益率 (APY)'].idxmax()]
                st.success(f"💡 数据建议：在 **{best_row['到期日']}** (DTE {best_row['剩余天数 (DTE)']}) 到期的合约年化收益率最高，约为 **{best_row['年化收益率 (APY)']:.2f}%**")
                
            else:
                st.warning(f"在最近的到期日中未找到行权价为 ${target_strike} 的期权合约，请调整行权价。")
                
        else:
            st.error("无法获取股票数据，请检查代码是否正确。")
            
    except Exception as e:
        st.error(f"发生错误: {e}")

else:
    st.info("请在左侧输入股票代码开始。")

# 页脚
st.markdown("---")
st.markdown("*注：数据来源于 Yahoo Finance，存在延迟。权利金取 (Bid+Ask)/2，实际交易价格可能不同。*")