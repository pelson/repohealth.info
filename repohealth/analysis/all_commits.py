import pandas as pd
import plotly.graph_objs as go


def all_commits_prep(payload):
    commits = pd.DataFrame.from_dict(payload['commits'])
    return commits


def all_commits_viz(commits):
    return go.Figure(data=[go.Scatter(
        x=commits['date'],
        y=commits['deletions'].count(),
        text=commits['sha'],
        name='Deletions'
    )])
