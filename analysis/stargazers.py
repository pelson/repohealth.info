import pandas as pd
import plotly.graph_objs as go


def stargazers_prep(payload):
    stargazers = pd.DataFrame.from_dict(payload['github']['stargazers'])
    stargazers['starred_at'] = pd.to_datetime(stargazers['starred_at'])
    return stargazers


def stargazers_viz(stargazers):
    if len(stargazers) == 0:
        stargazers = {'starred_at': [], 'login': []}
    stars = go.Scatter(
        x=stargazers['starred_at'],
        y=[i + 1 for i in range(len(stargazers['starred_at']))],
        text=stargazers['login'],
    )
    return go.Figure(data=[stars])
