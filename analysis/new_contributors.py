import pandas as pd
import plotly.graph_objs as go


def new_contributors_prep(payload):
    commits = pd.DataFrame.from_dict(payload['commits'])
    first_commits = commits.drop_duplicates(subset='email')
    return first_commits


def new_contributors_viz(data):
    new_contributors = go.Scatter(
        x=data['date'],
        y=[i + 1 for i in range(len(data['date']))],
        text=data['name'],
    )
    return go.Figure(data=[new_contributors])
