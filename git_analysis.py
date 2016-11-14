import datetime
import git
import pandas as pd
from io import StringIO
import json

def contributors(repo):
    max_samples = 30

    # Get all contributions, ordered by date.
    all_contribs = repo.git.log('--all', '--format=%aD|%aN|%aE', '--reverse')
    all_contribs = pd.read_csv(StringIO(all_contribs), sep='|', parse_dates=[0], infer_datetime_format=True, names=['Date', 'Name', 'Email'])

    # Drop all but the first commit for each user 
    first_commits = all_contribs.drop_duplicates(subset='Email')

    combined = lambda ds: ', '.join('{0.Name}|{0.Email}'.format(row) for index, row in ds.iterrows())
    commits_grouped = first_commits.set_index('Date').groupby(pd.TimeGrouper(freq='M'))
    
    isodt = lambda pd_dt: datetime.datetime.strftime(pd_dt, '%Y-%m-%dT%H:%M:%SZ')

    first_commit_counts = commits_grouped.apply(combined)
    first_commit_counts = first_commit_counts.to_frame('New contributors')
    first_commit_counts['Count'] = commits_grouped.count()['Name'].values
    results = {}

    first_commits = [{'date': isodt(row['Date']), 'name': row['Name'], 'email': row['Email']}
                      for _, row in first_commits.iterrows()]

    first_commits_grouped = []
    for index, rows in commits_grouped:
        first_commits_grouped.append({'T1': isodt(index),
                                      'count': len(rows),
                                      'first_contributions': [{'date': isodt(ind), 'name': row['Name'], 'email': row['Email']}
                                                               for ind, row in rows.iterrows()]})
    results['first_commit_T1M_groups'] = first_commits_grouped
    results['first_commits'] = first_commits

    return results


if __name__ == '__main__':
    repo = git.Repo('/Users/pelson/dev/iris')
    from pprint import pprint
    pprint(contributors(repo))
