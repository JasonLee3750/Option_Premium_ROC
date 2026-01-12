import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import random

# --- 1. 页面基础配置 ---
st.set_page_config(page_title="期权筛选器 (防封稳健版)", layout="wide")

st.title("🛡️ 期权目标收益筛选器 (防封修复版)")
st.markdown("""
**功能说明：** 此工具帮助您寻找满足**最低年化收益率**要求的**最安全**（离现价最远）行权价。
> **⚠️ 防封提示：** 为防止 Yahoo 封锁 IP，程序每扫描一个日期会自动暂停 1~2 秒，请耐心等待。
""")

# --- 2. 侧边栏：用户设置 ---
st.sidebar.header("🔎 筛选条件")
ticker_symbol = st.sidebar.text_input("股票代码 (Ticker)", value="NVDA").upper()
option_type = st.sidebar.selectbox("交易策略", ["Sell Put (Cash Secured)", "Sell Call (Covered)"])
target_return = st.sidebar.number_input("期待的最小年化收益率 (%)", value=15.0, step=1.0)
scan_limit = st.sidebar.slider("扫描最近到期日数量 (建议 <= 8)", 3, 12, 6)

if st.sidebar.button("🗑️ 清除数据缓存"):
    st.cache_data.clear()
    st.success("缓存已清除，下次查询将获取最新数据。")

# --- 3. 核心函数：带缓存的数据获取 ---
@st.cache_data(ttl=3600, show_spinner=False) 
def get_option_data(ticker, date_str, opt_type_str):
    """
    获取指定日期的期权链，并进行基础清洗。
    """
    try:
        # 随机延时 1.0 - 2.0 秒
        time.sleep(random.uniform(1.0, 2.0))
        
        stock = yf.Ticker(ticker)
        opt_chain = stock.option_chain(date_str)
        
        # 根据策略选择 Put 或 Call 链
        if "Put" in opt_type_str:
            chain = opt_chain.puts
        else:
            chain = opt_chain.calls
            
        # 过滤掉没有流动性的合约 (Bid > 0)
        chain = chain[chain['bid'] > 0].copy()
        
        if chain.empty:
            return None
            
        return chain
        
    except Exception as e:
        # 如果遇到 Rate Limit，通常会抛出异常
        if "Too Many Requests" in str(e):
            return "RATE_LIMIT"
        return None

# --- 4. 主程序逻辑 ---
if st.sidebar.button("🚀 开始筛选"):
    if not ticker_symbol:
        st.error("请输入股票代码！")
    else:
        try:
            # 第一步：获取当前股价
            stock = yf.Ticker(ticker_symbol)
            history = stock.history(period="1d")
            
            if history.empty:
                st.error(f"无法获取 {ticker_symbol} 的股价，请检查代码或网络。")
            else:
                current_price = history['Close'].iloc[-1]
                
                # 顶部仪表盘
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(f"{ticker_symbol} 当前股价", f"${current_price:.2f}")
                with col2:
                    strategy_text = "寻找最低 Strike (最抗跌)" if "Put" in option_type else "寻找最高 Strike (最抗涨)"
                    st.info(f"🎯 策略: {strategy_text} | 目标年化 ≥ {target_return}%")

                # 获取所有到期日
                expirations = stock.options
                if not expirations:
                    st.error("未找到期权链数据。")
                else:
                    analyze_dates = expirations[:scan_limit]
                    results = []
                    progress_bar = st.progress(0, text="准备开始扫描...")
                    
                    for i, date_str in enumerate(analyze_dates):
                        progress_val = (i + 1) / len(analyze_dates)
                        progress_bar.progress(progress_val, text=f"正在分析到期日: {date_str} ...")
                        
                        # 获取数据
                        chain = get_option_data(ticker_symbol, date_str, option_type)
                        
                        # --- 修复点：严格的数据类型检查 ---
                        
                        # 1. 先检查是不是字符串错误信息
                        if isinstance(chain, str) and chain == "RATE_LIMIT":
                            st.error("⚠️ Yahoo 拒绝了请求 (Rate Limited)。请稍等几分钟再试，或减少扫描数量。")
                            break
                        
                        # 2. 再检查是不是 None
                        if chain is None:
                            continue
                            
                        # 3. 最后检查 DataFrame 是否为空 (此时 chain 肯定是 DataFrame)
                        if chain.empty:
                            continue
                            
                        # --- 计算指标 ---
                        chain['premium'] = (chain['bid'] + chain['ask']) / 2
                        
                        if "Put" in option_type:
                            chain['capital'] = chain['strike']
                        else:
                            chain['capital'] = current_price
                        
                        exp_date = datetime.strptime(date_str, "%Y-%m-%d")
                        today = datetime.now()
                        dte = (exp_date - today).days
                        if dte <= 0: dte = 1
                        
                        chain['roi_annual'] = (chain['premium'] / chain['capital']) * (365 / dte) * 100
                        
                        # --- 筛选 ---
                        qualified = chain[chain['roi_annual'] >= target_return]
                        
                        if not qualified.empty:
                            if "Put" in option_type:
                                best_opt = qualified.sort_values(by='strike', ascending=True).iloc[0]
                                safety_gap = (current_price - best_opt['strike']) / current_price
                            else:
                                best_opt = qualified.sort_values(by='strike', ascending=False).iloc[0]
                                safety_gap = (best_opt['strike'] - current_price) / current_price
                                
                            results.append({
                                "到期日": date_str,
                                "DTE (天)": dte,
                                "建议行权价": best_opt['strike'],
                                "IV": f"{best_opt['impliedVolatility'] * 100:.1f}%" if 'impliedVolatility' in best_opt else "N/A",
                                "预估权利金": f"${best_opt['premium']:.2f}",
                                "年化收益率": f"{best_opt['roi_annual']:.2f}%",
                                "安全垫": f"{safety_gap * 100:.1f}%"
                            })
                    
                    progress_bar.empty()
                    
                    if results:
                        df_res = pd.DataFrame(results)
                        st.success(f"✅ 筛选完成！找到 {len(df_res)} 个符合条件的策略。")
                        
                        df_display = df_res.copy()
                        df_display["建议行权价"] = df_display["建议行权价"].apply(lambda x: f"${x:.1f}")
                        st.dataframe(df_display, use_container_width=True)
                        
                        st.subheader("🛡️ 安全垫趋势 (Bar Chart)")
                        df_chart = df_res.copy()
                        df_chart["Safety_Val"] = df_chart["安全垫"].str.rstrip('%').astype(float)
                        st.bar_chart(df_chart, x="到期日", y="Safety_Val")
                    else:
                        st.warning(f"在最近的 {scan_limit} 个到期日中，未找到年化收益率 ≥ {target_return}% 的合约。")
                        
        except Exception as e:
            st.error(f"发生未知错误: {e}")

else:
    st.info("👈 请在左侧调整参数，然后点击 '开始筛选'")
