import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# --- 页面配置 ---
st.set_page_config(page_title="期权收益计算器", layout="centered")

st.title("📈 期权卖方收益计算器")
st.caption("分析特定行权价在不同到期日的年化收益率")

# --- 侧边栏：输入区 ---
st.sidebar.header("参数设置")
ticker_symbol = st.sidebar.text_input("股票代码", value="NVDA").upper()
option_type = st.sidebar.selectbox("期权类型", ["Put (Sell)", "Call (Sell)"])
target_strike = st.sidebar.number_input("行权价 (Strike)", value=170.0, step=0.5)

st.sidebar.markdown("---")
# 新增：时间长度选择 (最多 12 个月)
time_horizon_months = st.sidebar.slider("时间跨度 (月)", min_value=1, max_value=12, value=3, help="选择查看未来几个月内的期权链 (最长1年)")

# --- 主程序逻辑 ---
if ticker_symbol:
    try:
        # 1. 获取实时股价
        stock = yf.Ticker(ticker_symbol)
        history = stock.history(period="1d")
        
        if not history.empty:
            current_price = history['Close'].iloc[-1]
            
            # --- 核心指标计算 (顶部仪表盘) ---
            if "Put" in option_type:
                mos = (current_price - target_strike) / current_price * 100
                mos_label = "跌破缓冲 (安全垫)"
                color = "normal" if mos > 0 else "inverse"
            else:
                mos = (target_strike - current_price) / current_price * 100
                mos_label = "上涨缓冲 (安全垫)"
                color = "normal" if mos > 0 else "inverse"
            
            # --- 顶部三列布局 ---
            st.subheader("核心指标")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("当前股价", f"${current_price:.2f}")
            with col2:
                st.metric("目标行权价", f"${target_strike:.2f}")
            with col3:
                st.metric(mos_label, f"{mos:.2f}%", delta=None)

            st.markdown("---") 

            # --- 2. 获取并过滤期权链 ---
            expirations = stock.options
            if not expirations:
                st.error("未找到期权链数据。")
                st.stop()

            # 计算最大天数限制
            max_days = time_horizon_months * 30 
            
            # 筛选符合时间范围的到期日
            analyze_dates = []
            today = datetime.now()
            
            for date_str in expirations:
                exp_date = datetime.strptime(date_str, "%Y-%m-%d")
                delta_days = (exp_date - today).days
                
                # 只保留: 未过期 且 在用户设定的天数范围内的
                if 0 < delta_days <= max_days:
                    analyze_dates.append(date_str)

            if not analyze_dates:
                st.warning(f"在未来 {time_horizon_months} 个月内未找到到期日。")
                st.stop()

            # --- 3. 抓取数据 ---
            with st.spinner(f'正在分析未来 {time_horizon_months} 个月 ({len(analyze_dates)} 个到期日) 的数据...'):
                
                data_list = []
                
                for date_str in analyze_dates:
                    try:
                        opt_chain = stock.option_chain(date_str)
                        options_df = opt_chain.puts if "Put" in option_type else opt_chain.calls
                        
                        # 找到对应 Strike 的合约
                        contract = options_df[options_df['strike'] == target_strike]
                        
                        if not contract.empty:
                            contract = contract.iloc[0]
                            
                            # 提取数据
                            bid = contract['bid']
                            ask = contract['ask']
                            last = contract['lastPrice']
                            # 使用 Mid Price，如果没有流动性则用 Last
                            premium = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
                            
                            # IV
                            iv_raw = contract.get('impliedVolatility', 0)
                            
                            # DTE
                            exp_date = datetime.strptime(date_str, "%Y-%m-%d")
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
                    except Exception:
                        continue # 跳过单个获取失败的日期
                
                if data_list:
                    df = pd.DataFrame(data_list)
                    
                    # 格式化用于显示的列
                    df_display = df.copy()
                    df_display["年化(APY)"] = df_display["年化(APY)"].apply(lambda x: f"{x:.2f}%")
                    
                    st.subheader(f"📊 收益期限结构 (Strike: ${target_strike})")
                    st.table(df_display)
                    
                    # 趋势图
                    st.line_chart(df, x="到期日", y="年化(APY)")
                    st.caption(f"显示范围：未来 {time_horizon_months} 个月")
                    
                else:
                    st.warning(f"在选定时间内未找到行权价为 ${target_strike} 的活跃合约。")

    except Exception as e:
        st.error(f"发生错误: {e}")
else:
    st.info("请输入代码开始")
