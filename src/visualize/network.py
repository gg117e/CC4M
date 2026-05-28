import plotly.graph_objects as go
import math
import pandas as pd
import itertools

def create_network_graph(services_data, project_name, language, df=None):
    """
    services.jsonのデータからサービス間依存関係ネットワークグラフを作成する
    
    Args:
        services_data (dict): services.jsonの中身
        project_name (str): プロジェクト名
        language (str): 言語
        df (pd.DataFrame, optional): フィルタリング済みのクローンデータ。指定された場合、これに基づいてエッジを再計算する。
        
    Returns:
        go.Figure: ネットワークグラフ
    """
    if not services_data:
        return go.Figure().update_layout(title="No data available")

    # データ抽出
    services = services_data.get('services', [])
    if not services:
        # servicesキーがない場合はfile_countsから取得
        file_counts = services_data.get('languages', {}).get(language, {}).get('file_counts', {})
        services = sorted(list(file_counts.keys()))
    
    # 言語固有のデータを取得
    lang_data = services_data.get('languages', {}).get(language, {})
    file_counts = lang_data.get('file_counts', {})
    
    # インターサービス・クローン数 (エッジ)
    inter_counts = {}
    
    if df is not None and not df.empty:
        # DataFrameからエッジを再計算
        # service_x, service_y のペアをカウント
        # relation == 'inter' のものだけ対象
        inter_df = df[df['relation'] == 'inter']
        
        # ペアごとにカウント (s1 < s2 で正規化)
        for _, row in inter_df.iterrows():
            s1 = row.get('service_x')
            s2 = row.get('service_y')
            if s1 and s2 and s1 != 'unknown' and s2 != 'unknown' and s1 != s2:
                key = f"{min(s1, s2)}--{max(s1, s2)}"
                inter_counts[key] = inter_counts.get(key, 0) + 1
    else:
        # services.json の counts.inter を使用 (フォールバック)
        # counts.inter は "ServiceA--ServiceB": count の形式
        inter_counts = services_data.get('counts', {}).get('inter', {})
    
    if not services:
        return go.Figure().update_layout(title="No services found")

    # ノード配置 (円形レイアウト)
    N = len(services)
    R = 10  # 半径
    node_x = []
    node_y = []
    node_text = []
    node_size = []
    node_color = []
    
    service_to_pos = {}
    
    # サービスをソート (類似サービスが近くになるように名前順)
    sorted_services = sorted(services)
    
    for i, service in enumerate(sorted_services):
        angle = 2 * math.pi * i / N
        x = R * math.cos(angle)
        y = R * math.sin(angle)
        
        node_x.append(x)
        node_y.append(y)
        service_to_pos[service] = (x, y)
        
        # ノード情報
        count = file_counts.get(service, 0)
        node_text.append(f"{service}<br>Files: {count}")
        # サイズはファイル数の対数などで調整 (最小10, 最大50くらい)
        size = 10 + (math.log(count + 1) * 5)
        node_size.append(size)
        node_color.append(i) # 色はインデックスで適当に分散

    # エッジ生成
    edge_x = []
    edge_y = []
    edge_text = [] # ホバー用 (Lineには出にくいが)
    
    # エッジの太さを調整するためのリスト
    edge_weights = []
    
    max_weight = 0
    if inter_counts:
        max_weight = max(inter_counts.values())
    
    # Plotlyで太さを変えるには、Traceを分けるか、一定にする必要がある。
    # ここではシンプルに、重みごとにTraceを分けるか、あるいは単一Traceで太さ一定にするか。
    # 視認性のため、太さは一定にし、透明度やホバー情報で重みを表現するアプローチをとる。
    # もしくは、重要なエッジだけ描画する。
    
    # 今回は「太さ」を表現したいので、重みごとにTraceを生成するアプローチは重くなる可能性がある。
    # 代わりに、すべてのエッジを1つのTraceで描き、太さは平均的なものにするか、
    # 上位のエッジのみ太くするなどの工夫が必要。
    # ここではシンプルに「全エッジをグレーで描画」し、太さは固定とする。
    # (PlotlyのScatter(mode='lines')は単一のwidthしか持てないため)
    
    # 重み付きエッジを描画するために、不透明度(opacity)を重みに比例させる
    # しかし1つのTraceではopacityも単一。
    # よって、エッジを「重み」でグループ化して、数段階のTraceに分けるのが現実的。
    
    edge_traces = []
    
    # エッジを重みでバケット分け (例: 1-5, 6-20, 21+)
    edges_by_weight = []
    for key, weight in inter_counts.items():
        parts = key.split('--')
        if len(parts) != 2:
            continue
        s1, s2 = parts
        if s1 not in service_to_pos or s2 not in service_to_pos:
            continue
            
        edges_by_weight.append({
            's1': s1, 's2': s2, 'weight': weight
        })
    
    # 重みでソート
    edges_by_weight.sort(key=lambda x: x['weight'])
    
    # 最大重みに基づいて正規化し、Traceを作成
    # ここではシンプルに、すべてのエッジを1つのTraceで描画し、
    # ホバー時に情報を出すのは難しいので、ノードのホバーで情報を補完する方針とする。
    # エッジは「つながりがある」ことの可視化に留める。
    
    for edge in edges_by_weight:
        x0, y0 = service_to_pos[edge['s1']]
        x1, y1 = service_to_pos[edge['s2']]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1, color='#888'),
        hoverinfo='none',
        mode='lines',
        opacity=0.5
    )
    
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        hoverinfo='text',
        text=[s.split('/')[-1] for s in sorted_services], # ラベルは短く
        hovertext=node_text,
        textposition="top center",
        marker=dict(
            showscale=True,
            colorscale='YlGnBu',
            reversescale=True,
            color=node_color,
            size=node_size,
            colorbar=dict(
                thickness=15,
                title='Service Index',
                xanchor='left',
                titleside='right'
            ),
            line_width=2))

    fig = go.Figure(data=[edge_trace, node_trace],
             layout=go.Layout(
                title=f'Service Dependency Network ({project_name})',
                titlefont_size=16,
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20,l=5,r=5,t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                )
                
    # 注釈: エッジの数はクローン共有数を表す
    fig.add_annotation(
        text=f"Total Services: {len(services)}<br>Total Connections: {len(edges_by_weight)}",
        xref="paper", yref="paper",
        x=0, y=0, showarrow=False
    )
    
    return fig
