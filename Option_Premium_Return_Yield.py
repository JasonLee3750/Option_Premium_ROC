import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="期权计算器", layout="centered")

st.title("📈 期权卖方收益计算器")

# --- 侧边栏 ---
st.sidebar.header("参数设置")
ticker_symbol = st.sidebar.text_input("股票代码", value="NVDA").upper()
option_type = st.sidebar.selectbox("期权类型", ["Put (Sell)", "Call (Sell)"])
target_strike = st.sidebar.number_input("行权价 (Strike)", value=170.0, step=0.5)

if ticker_symbol:
    try:
        # 1. 获取数据
        stock = yf.Ticker(ticker_symbol)
        history = stock.history(period="1d")
        
        if not history.empty:
            current_price = history['Close'].iloc[-1]
            
            # --- 核心计算 (移到循环外) ---
            # 计算安全垫 (Margin of Safety)
            if "Put" in option_type:
                mos = (current_price - target_strike) / current_price * 100
                mos_label = "跌破缓冲 (安全垫)"
            else:
                mos = (target_strike - current_price) / current_price * 100
                mos_label = "上涨缓冲 (安全垫)"
            
            # --- 顶部仪表盘区域 ---
            st.subheader("核心指标")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("当前股价", f"${current_price:.2f}")
            with col2:
                st.metric("目标行权价", f"${target_strike:.2f}")
            with col3:
                # 假如安全垫为正，显示绿色；反之红色
                st.metric(mos_label, f"{mos:.2f}%", delta=None)

            st.markdown("---") # 分割线

            # --- 获取期权链 ---
            expirations = stock.options
            
            with st.spinner('正在分析期权链及 IV...'):
                data_list = []
                analyze_dates = expirations[:8]
                
                for date_str in analyze_dates:
                    opt_chain = stock.option_chain(date_str)
                    options_df = opt_chain.puts if "Put" in option_type else opt_chain.calls
                    
                    contract = options_df[options_df['strike'] == target_strike]
                    
                    if not contract.empty:
                        contract = contract.iloc[0]
                        
                        # 权利金
                        bid = contract['bid']
                        ask = contract['ask']
                        last = contract['lastPrice']
                        premium = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
                        
                        # IV
                        iv_raw = contract['impliedVolatility']
                        
                        # DTE
                        exp_date = datetime.strptime(date_str, "%Y-%m-%d")
                        today = datetime.now()
                        dte = (exp_date - today).days
                        if dte <= 0: dte = 1
                        
                        # 收益率
                        capital = target_strike if "Put" in option_type else current_price
                        roc = premium / capital
                        annualized_return = roc * (365 / dte) * 100
                        
                        data_list.append({
                            "到期日": date_str,
                            "DTE": dte,
                            "IV": f"{iv_raw * 100:.1f}%",
                            "权利金": f"${premium:.2f}",
                            "年化(APY)": annualized_return
                        })
                
                if data_list:
                    df = pd.DataFrame(data_list)
                    # 格式化
                    df_display = df.copy()
                    df_display["年化(APY)"] = df_display["年化(APY)"].apply(lambda x: f"{x:.2f}%")
                    
                    st.subheader("期权链收益表")
                    st.table(df_display)
                    
                    # 趋势图
                    st.line_chart(df, x="到期日", y="年化(APY)")
                    
                else:
                    st.warning(f"未找到 ${target_strike} 的合约。")

    except Exception as e:
        st.error(f"获取数据失败: {e}")
else:
    st.info("请输入代码")
