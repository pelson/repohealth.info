import datetime
import numpy as np
import pandas as pd
import plotly.graph_objs as go


def last_commits_prep(payload):
    commits = pd.DataFrame.from_dict(payload['commits'])
    commits['date'] = pd.to_datetime(commits['date'])
    now = datetime.datetime.utcnow()
    commits['days'] = (now - commits['date']).apply(lambda td: td.total_seconds() / 60 / 60 / 24)
    last_commits = commits.drop_duplicates(subset='email', keep='last')
    last_commits = last_commits.sort_values(by='days', ascending=True)
    return last_commits


def last_commits_viz(last_commits):
    new_contributors = go.Scatter(
        x=last_commits['days'],
        y=np.arange(len(last_commits)) + 1,
        text=last_commits['name'],
    )
    layout = go.Layout(xaxis=dict(autorange='reversed'))
    return go.Figure(data=[new_contributors], )

