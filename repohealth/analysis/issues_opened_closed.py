import pandas as pd
import plotly.graph_objs as go


def issues_prep(payload):
    issues = pd.DataFrame.from_dict(payload['github']['issues'])
    issues['created_at'] = pd.to_datetime(issues['created_at'])
    issues['closed_at'] = pd.to_datetime(issues['closed_at'])

    issues_open = issues.sort_values(by='created_at')

    issues_closed = issues.sort_values(by='closed_at')
    return issues_open, issues_closed[issues_closed['closed_at'].notnull()]


def issues_viz(issues_open_and_closed):
    issues_open, issues_closed = issues_open_and_closed
    v_issues_open = go.Scatter(
        x=issues_open['created_at'],
        y=[i + 1 for i in range(len(issues_open['created_at']))],
        text=issues_open['user/login'],
        name='Issues opened'
    )
    v_issues_closed = go.Scatter(
        x=issues_closed['closed_at'],
        y=[i + 1 for i in range(len(issues_closed['closed_at']))],
        text=issues_closed['user/login'],
        name='Issues closed'
    )
    return go.Figure(data=[v_issues_open, v_issues_closed])
