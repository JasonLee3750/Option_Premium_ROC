import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="期权收益目标筛选器", layout="wide")

st.title("🎯 期权目标收益筛选器 (Smart Seeker)")
st.markdown("此工具根据您设定的**最低年化收益率**，自动寻找每个到期日中**最安全**（即离现价最远）的行权价。")

# --- 侧边栏：用户输入 ---
st.sidebar.header("筛选条件")
ticker_symbol = st.sidebar.text_input("股票代码 (Ticker)", value="NVDA").upper()
option_type = st.sidebar.selectbox("交易策略", ["Sell Put (Cash Secured)", "Sell Call (Covered)"])
target_return = st.sidebar.number_input("期待的最小年化收益率 (%)", value=15.0, step=1.0)

# --- 核心逻辑 ---
if st.sidebar.button("开始筛选 (Start Seek)"):
    if not ticker_symbol:
        st.error("请输入股票代码")
    else:
        try:
            # 1. 获取基础数据
            stock = yf.Ticker(ticker_symbol)
            history = stock.history(period="1d")
            
            if history.empty:
                st.error(f"无法获取 {ticker_symbol} 的数据，请检查代码。")
            else:
                current_price = history['Close'].iloc[-1]
                
                # 显示实时行情
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(f"{ticker_symbol} 当前股价", f"${current_price:.2f}")
                with col2:
                    target_text = "寻找最低 Strike (最抗跌)" if "Put" in option_type else "寻找最高 Strike (最抗涨)"
                    st.info(f"策略目标: {target_text} 且年化 ≥ {target_return}%")

                # 获取到期日
                expirations = stock.options
                if not expirations:
                    st.error("未找到期权链数据。")
                else:
                    # 限制查询范围，避免等待太久 (查最近 10 个到期日)
                    analyze_dates = expirations[:10]
                    
                    results = []
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, date_str in enumerate(analyze_dates):
                        # 更新进度
                        progress_bar.progress((i + 1) / len(analyze_dates))
                        status_text.text(f"正在扫描到期日: {date_str} ...")
                        
                        # 计算 DTE
                        exp_date = datetime.strptime(date_str, "%Y-%m-%d")
                        today = datetime.now()
                        dte = (exp_date - today).days
                        if dte <= 0: dte = 1 # 避免除零
                        
                        # 获取期权链
                        try:
                            opt_chain = stock.option_chain(date_str)
                            chain = opt_chain.puts if "Put" in option_type else opt_chain.calls
                        except:
                            continue # 跳过获取失败的日期
                        
                        # --- 批量计算收益率 ---
                        # 1. 清洗数据：去掉没有流动性的合约 (Bid > 0)
                        chain = chain[chain['bid'] > 0].copy()
                        
                        if chain.empty:
                            continue

                        # 2. 计算权利金 (Mid Price)
                        chain['premium'] = (chain['bid'] + chain['ask']) / 2
                        
                        # 3. 确定投入资本 (Capital)
                        # Put: 保证金 = Strike
                        # Call: 成本 = 当前股价 (Covered Call 基于持有正股)
                        if "Put" in option_type:
                            chain['capital'] = chain['strike']
                        else:
                            chain['capital'] = current_price
                        
                        # 4. 计算年化收益率
                        # ROC = Premium / Capital
                        # Annualized = ROC * (365 / DTE) * 100
                        chain['roi_annual'] = (chain['premium'] / chain['capital']) * (365 / dte) * 100
                        
                        # --- 筛选与优选逻辑 ---
                        # 1. 过滤掉不满足用户收益要求的
                        qualified = chain[chain['roi_annual'] >= target_return]
                        
                        if not qualified.empty:
                            # 2. 挑选"最安全"的 Strike
                            if "Put" in option_type:
                                # Sell Put: 越低的 Strike 越安全
                                # 既然已经过滤了 >= 目标收益，我们取其中 Strike 最小的
                                best_option = qualified.sort_values(by='strike', ascending=True).iloc[0]
                                safety_gap = (current_price - best_option['strike']) / current_price
                            else:
                                # Sell Call: 越高的 Strike 越安全 (不容易被行权)
                                # 取其中 Strike 最大的
                                best_option = qualified.sort_values(by='strike', ascending=False).iloc[0]
                                safety_gap = (best_option['strike'] - current_price) / current_price
                            
                            results.append({
                                "到期日": date_str,
                                "DTE (天数)": dte,
                                "建议行权价": best_option['strike'],
                                "当前 IV": f"{best_option['impliedVolatility'] * 100:.1f}%",
                                "预估权利金": f"${best_option['premium']:.2f}",
                                "年化收益率": f"{best_option['roi_annual']:.2f}%",
                                "安全垫 (距离)": f"{safety_gap * 100:.1f}%"
                            })
                    
                    # 清理进度条
                    progress_bar.empty()
                    status_text.empty()
                    
                    # --- 展示结果 ---
                    if results:
                        df_results = pd.DataFrame(results)
                        
                        st.success(f"筛选完成！找到 {len(df_results)} 个符合条件的到期日策略。")
                        
                        # 格式化一下行权价，让它看起来好看点
                        df_display = df_results.copy()
                        df_display["建议行权价"] = df_display["建议行权价"].apply(lambda x: f"${x:.1f}")
                        
                        # 展示表格
                        st.dataframe(df_display, use_container_width=True)
                        
                        # 可视化：展示每一期"能达到目标收益的最安全行权价"的位置
                        st.subheader("🛡️ 安全垫趋势 (越高越安全)")
                        
                        # 为了画图，我们需要把百分比字符串转回数字
                        df_chart = df_results.copy()
                        df_chart["Safety_Num"] = df_chart["安全垫 (距离)"].str.rstrip('%').astype(float)
                        
                        st.bar_chart(df_chart, x="到期日", y="Safety_Num")
                        st.caption("注：柱状图越高，代表该策略距离当前股价越远，被行权的风险越低。")
                        
                    else:
                        st.warning(f"在最近的到期日中，没有找到年化收益率 ≥ {target_return}% 的合约。建议降低收益目标或选择波动率更高的股票。")

        except Exception as e:
            st.error(f"发生错误: {e}")
else:
    st.info("请在左侧设置目标并点击 '开始筛选'")