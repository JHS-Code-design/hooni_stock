import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx


def build_network_graph(nodes: list, edges: list) -> go.Figure:
    """networkx spring_layout → Plotly 네트워크 그래프"""
    if not nodes or not edges:
        return go.Figure().add_annotation(text="연관 종목 없음", showarrow=False)

    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"], **n)
    for e in edges:
        G.add_edge(e["source"], e["target"], weight=e["weight"])

    pos = nx.spring_layout(G, seed=42, k=1.5)

    # 섹터별 색상
    sectors = list({n["sector"] for n in nodes})
    color_map = {s: px.colors.qualitative.Plotly[i % 10] for i, s in enumerate(sectors)}

    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=1, color="#888"),
        hoverinfo="none",
    )

    node_x = [pos[n["id"]][0] for n in nodes]
    node_y = [pos[n["id"]][1] for n in nodes]
    node_colors = [color_map[n["sector"]] for n in nodes]
    node_sizes = [20 if n.get("is_watch") else 12 for n in nodes]
    node_text = [f"{n['name']}<br>{n['sector']}" for n in nodes]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=[n["name"] for n in nodes],
        textposition="top center",
        hovertext=node_text,
        hoverinfo="text",
        marker=dict(size=node_sizes, color=node_colors, line=dict(width=1, color="#fff")),
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            showlegend=False,
            hovermode="closest",
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
            title="종목 연관 네트워크",
        ),
    )
    return fig


def build_heatmap(corr_matrix: pd.DataFrame, watch_symbols: list) -> go.Figure:
    """상관계수 히트맵"""
    if corr_matrix.empty:
        return go.Figure().add_annotation(text="데이터 없음", showarrow=False)

    # 관심 종목 기준으로 슬라이싱
    cols = [s for s in watch_symbols if s in corr_matrix.columns]
    if not cols:
        cols = corr_matrix.columns[:20].tolist()

    sub = corr_matrix.loc[corr_matrix.index.isin(corr_matrix.columns), cols]

    fig = go.Figure(go.Heatmap(
        z=sub.values,
        x=sub.columns.tolist(),
        y=sub.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        text=sub.round(2).values,
        texttemplate="%{text}",
        hovertemplate="%{y} ↔ %{x}: %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(
        title="수익률 상관계수 히트맵",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def build_treemap(listing: pd.DataFrame) -> go.Figure:
    """섹터별 종목 트리맵"""
    if listing.empty:
        return go.Figure().add_annotation(text="데이터 없음", showarrow=False)

    required = {"Sector", "Name"}
    if not required.issubset(listing.columns):
        return go.Figure().add_annotation(text="섹터 데이터 없음", showarrow=False)

    df = listing.dropna(subset=["Sector", "Name"]).copy()
    df["count"] = 1

    fig = px.treemap(
        df,
        path=["Sector", "Name"],
        values="count",
        color="Sector",
        color_discrete_sequence=px.colors.qualitative.Plotly,
    )
    fig.update_layout(
        title="섹터별 종목 구성",
        paper_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def build_comparison_chart(prices_df: pd.DataFrame, symbols: list, names: dict) -> go.Figure:
    """정규화 주가 비교 차트 (기준=100)"""
    if prices_df.empty:
        return go.Figure().add_annotation(text="가격 데이터 없음", showarrow=False)

    fig = go.Figure()
    for sym in symbols:
        if sym not in prices_df.columns:
            continue
        series = prices_df[sym].dropna()
        if series.empty:
            continue
        normalized = series / series.iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=normalized.index,
            y=normalized.values,
            name=names.get(sym, sym),
            mode="lines",
        ))

    fig.update_layout(
        title="정규화 주가 비교 (기준=100)",
        yaxis_title="지수",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        legend=dict(bgcolor="#262730"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig
