import pandas as pd
import plotly.graph_objs as go


def stargazers_prep(payload):
    print(payload['github']['stargazers'])
    stargazers = pd.DataFrame.from_dict(payload['github']['stargazers'])
    if len(stargazers) == 0:
        stargazers = {'starred_at': [], 'user/login': []}
    else:
        stargazers['starred_at'] = pd.to_datetime(stargazers['starred_at'])
        stargazers.sort_values(by='starred_at', inplace=True)
    return stargazers


def stargazers_viz(stargazers):
    stars = go.Scatter(
        x=stargazers['starred_at'],
        y=[i + 1 for i in range(len(stargazers['starred_at']))],
        text=stargazers['user/login'],
    )
    return go.Figure(data=[stars])
