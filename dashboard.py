import streamlit as st
import pandas as pd
import plotly.express as px
from db.database import engine

# --- Streamlit Page Config ---
st.set_page_config(
    page_title="Lichess Big Data Dashboard",
    page_icon="♟️",
    layout="wide"
)

st.title("♟️ Lichess Big Data Dashboard")
st.markdown("Welcome to the visualization layer of our Lichess Big Data project! This dashboard connects directly to our PostgreSQL database to visualize chess analytics.")

# --- Data Loading Function (with Caching) ---
# We cache the data for 10 minutes (600s) to avoid hitting the DB too hard on every interaction
@st.cache_data(ttl=600)
def load_opening_stats():
    query = """
    SELECT 
        opening,
        COUNT(*) as total_games,
        SUM(CASE WHEN result = '1-0' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as white_win_pct,
        SUM(CASE WHEN result = '0-1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as black_win_pct,
        SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as draw_pct
    FROM games
    WHERE opening IS NOT NULL
    GROUP BY opening
    ORDER BY total_games DESC
    LIMIT 20
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

@st.cache_data(ttl=600)
def load_elo_distribution():
    query = """
    SELECT white_elo
    FROM games
    WHERE white_elo IS NOT NULL
    LIMIT 10000
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

@st.cache_data(ttl=600)
def load_time_stats():
    query = """
    SELECT total_moves, white_avg_think_time
    FROM games
    WHERE white_avg_think_time IS NOT NULL AND total_moves IS NOT NULL
    LIMIT 5000
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

@st.cache_data(ttl=600)
def load_overall_results():
    query = """
    SELECT 
        CASE 
            WHEN result = '1-0' THEN 'White Win'
            WHEN result = '0-1' THEN 'Black Win'
            WHEN result = '1/2-1/2' THEN 'Draw'
            ELSE 'Other'
        END as result_label,
        COUNT(*) as total
    FROM games
    WHERE result IN ('1-0', '0-1', '1/2-1/2')
    GROUP BY result
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

@st.cache_data(ttl=600)
def load_draw_rate_by_elo():
    query = """
    SELECT 
        (white_elo / 100) * 100 as elo_bracket,
        COUNT(*) as total_games,
        SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as draw_pct
    FROM games
    WHERE white_elo IS NOT NULL 
      AND white_elo >= 1000 
      AND white_elo <= 2900
    GROUP BY elo_bracket
    HAVING COUNT(*) > 50
    ORDER BY elo_bracket
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

@st.cache_data(ttl=600)
def load_openings_by_elo():
    query_low = """
    SELECT 'Beginner (<1500)' as bracket, opening, COUNT(*) as total_games
    FROM games
    WHERE white_elo < 1500 AND opening IS NOT NULL
    GROUP BY opening
    ORDER BY total_games DESC
    LIMIT 5
    """
    query_high = """
    SELECT 'Advanced (>2000)' as bracket, opening, COUNT(*) as total_games
    FROM games
    WHERE white_elo > 2000 AND opening IS NOT NULL
    GROUP BY opening
    ORDER BY total_games DESC
    LIMIT 5
    """
    with engine.connect() as conn:
        df_low = pd.read_sql(query_low, conn)
        df_high = pd.read_sql(query_high, conn)
    return pd.concat([df_low, df_high])


# --- UI Layout ---
col_pie, col_elo = st.columns(2)

with col_pie:
    st.subheader("Overall Game Results")
    df_results = load_overall_results()
    if not df_results.empty:
        fig_pie = px.pie(
            df_results, 
            values='total', 
            names='result_label',
            title='White vs Black vs Draw',
            color='result_label',
            color_discrete_map={'White Win': '#e0e0e0', 'Black Win': '#424242', 'Draw': '#9e9e9e'},
            hole=0.3 # makes it a donut chart, looks a bit more modern
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No data available.")

with col_elo:
    st.subheader("Player ELO Distribution")
    df_elo = load_elo_distribution()
    
    if not df_elo.empty:
        fig2 = px.histogram(
            df_elo, 
            x='white_elo', 
            nbins=50,
            title="Distribution of White Player ELO Ratings",
            color_discrete_sequence=['#4CAF50']
        )
        fig2.update_layout(xaxis_title="ELO Rating", yaxis_title="Count")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No data available yet.")

st.divider()

st.subheader("Top 20 Openings: Win Rates")
df_openings = load_opening_stats()

if not df_openings.empty:
    # Melt the dataframe for easy plotting with plotly express
    df_melted = df_openings.melt(
        id_vars=['opening', 'total_games'],
        value_vars=['white_win_pct', 'black_win_pct', 'draw_pct'],
        var_name='Result', 
        value_name='Percentage'
    )
    # Clean up labels
    df_melted['Result'] = df_melted['Result'].map({
        'white_win_pct': 'White Win',
        'black_win_pct': 'Black Win',
        'draw_pct': 'Draw'
    })
    
    # We need to map colors carefully so white is light and black is dark
    fig1 = px.bar(
        df_melted, 
        x='opening', 
        y='Percentage', 
        color='Result',
        color_discrete_map={'White Win': '#e0e0e0', 'Black Win': '#424242', 'Draw': '#9e9e9e'},
        title="Win/Draw/Loss % by Opening",
        barmode='stack'
    )
    # Update layout to make it readable
    fig1.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig1, use_container_width=True)
else:
    st.info("No data available yet. Please load some games using the ETL pipeline.")

st.divider()

st.subheader("Time Management (Avg Think Time vs Total Moves)")
df_time = load_time_stats()
if not df_time.empty:
    fig3 = px.scatter(
        df_time,
        x='total_moves',
        y='white_avg_think_time',
        opacity=0.5,
        title="White Avg Think Time (sec) per Total Moves in Game",
        color_discrete_sequence=['#2196F3']
    )
    fig3.update_layout(xaxis_title="Total Moves", yaxis_title="Avg Think Time (Seconds)")
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No time data available yet. Time annotations might be missing in this dataset.")

st.divider()

# --- New Advanced Analytics Row ---
col_draws, col_ops = st.columns(2)

with col_draws:
    st.subheader("Draw Rate vs ELO Bracket")
    df_draws = load_draw_rate_by_elo()
    if not df_draws.empty:
        fig_draws = px.line(
            df_draws, 
            x='elo_bracket', 
            y='draw_pct',
            markers=True,
            title='Percentage of Drawn Games by ELO Bracket',
            color_discrete_sequence=['#FF9800']
        )
        fig_draws.update_layout(xaxis_title="ELO Bracket (Rounded to 100)", yaxis_title="Draw Rate (%)")
        st.plotly_chart(fig_draws, use_container_width=True)
    else:
        st.info("No data available.")

with col_ops:
    st.subheader("Top 5 Openings: Beginners vs Advanced")
    df_ops_elo = load_openings_by_elo()
    if not df_ops_elo.empty:
        fig_ops = px.bar(
            df_ops_elo,
            x='bracket',
            y='total_games',
            color='opening',
            barmode='group',
            title='Most Popular Openings by Skill Level'
        )
        fig_ops.update_layout(xaxis_title="Skill Level", yaxis_title="Total Games")
        st.plotly_chart(fig_ops, use_container_width=True)
    else:
        st.info("No data available.")
