import pandas as pd
import plotly.graph_objs as go


def commit_LOC_delta_prep(payload):
    commits = pd.DataFrame.from_dict(payload['commits'])
    return commits


def commit_LOC_delta_viz(commits):
    add = sub = go.Scatter(
        x=commits['date'],
        y=commits['insertions'].cumsum(),
        text=commits['sha'],
        name='Insertions'
    )
    sub = go.Scatter(
        x=commits['date'],
        y=commits['deletions'].cumsum(),
        name='Deletions'
    )
    fig = go.Figure(data=[add, sub])
    return fig
