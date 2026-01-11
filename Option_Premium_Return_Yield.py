import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 页面设置 ---
st.set_page_config(page_title="期权收益计算器", layout="centered") # 手机端建议用 centered

st.title("📈 期权卖方收益计算器")

# --- 侧边栏：输入区 ---
st.sidebar.header("参数设置")
ticker_symbol = st.sidebar.text_input("股票代码", value="NVDA").upper()
option_type = st.sidebar.selectbox("期权类型", ["Put (Sell)", "Call (Sell)"])
target_strike = st.sidebar.number_input("行权价 (Strike)", value=170.0, step=0.5)

# --- 主程序逻辑 ---
if ticker_symbol:
    try:
        # 1. 获取实时股价
        stock = yf.Ticker(ticker_symbol)
        history = stock.history(period="1d")
        
        if not history.empty:
            current_price = history['Close'].iloc[-1]
            
            # 显示当前股价 (大字体)
            st.metric(label=f"{ticker_symbol} 现价", value=f"${current_price:.2f}")
            
            # 2. 获取期权链
            expirations = stock.options
            
            # 进度提示
            with st.spinner(f'正在分析 {ticker_symbol} ${target_strike} 的期权链...'):
                
                data_list = []
                analyze_dates = expirations[:8] # 只看最近8个到期日
                
                for date_str in analyze_dates:
                    # 获取该日期的期权数据
                    opt_chain = stock.option_chain(date_str)
                    options_df = opt_chain.puts if "Put" in option_type else opt_chain.calls
                    
                    # 找到对应 Strike 的合约
                    contract = options_df[options_df['strike'] == target_strike]
                    
                    if not contract.empty:
                        contract = contract.iloc[0]
                        
                        # 计算权利金 (取中间价)
                        bid = contract['bid']
                        ask = contract['ask']
                        last = contract['lastPrice']
                        premium = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
                        
                        # 计算时间 DTE
                        exp_date = datetime.strptime(date_str, "%Y-%m-%d")
                        today = datetime.now()
                        dte = (exp_date - today).days
                        if dte <= 0: dte = 1
                        
                        # 计算资金占用 (用于后台计算收益率)
                        capital = target_strike if "Put" in option_type else current_price
                        
                        # 计算年化
                        roc = premium / capital
                        annualized_return = roc * (365 / dte) * 100
                        
                        # 安全垫计算
                        if "Put" in option_type:
                            mos = (current_price - target_strike) / current_price * 100
                        else:
                            mos = (target_strike - current_price) / current_price * 100

                        # --- 构建表格数据 (已移除不需要的列) ---
                        data_list.append({
                            "到期日": date_str,
                            "DTE": dte, # 简写剩余天数，方便手机看
                            "权利金": f"${premium:.2f}",
                            "安全垫": f"{mos:.1f}%",
                            "年化(APY)": annualized_return # 保持数字格式用于排序
                        })
                
                if data_list:
                    df = pd.DataFrame(data_list)
                    
                    # 格式化年化收益率显示
                    df_display = df.copy()
                    df_display["年化(APY)"] = df_display["年化(APY)"].apply(lambda x: f"{x:.2f}%")
                    
                    # --- 显示结果 ---
                    # 动态标题，补充缺失的 Strike 信息
                    st.subheader(f"📊 收益表 (Strike: ${target_strike})")
                    st.table(df_display) # 使用 table 组件展示所有数据
                    
                    # 手机端看图表
                    st.line_chart(df, x="到期日", y="年化(APY)")
                    
                else:
                    st.warning(f"未找到 ${target_strike} 的合约数据。")

    except Exception as e:
        st.error(f"发生错误，请检查股票代码: {e}")
else:
    st.info("请输入代码开始")
