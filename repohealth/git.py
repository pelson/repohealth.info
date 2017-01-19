import datetime
import git
import pandas as pd
from io import StringIO
import json


def commits(repo):
     # Get all contributions, ordered by date.
    log_output = repo.git.log('--all', '--format=%ai|%aN|%aE|%h|', '--reverse', '--shortstat')
    commit_lines = []
    commit_has_stat = False
    for line in log_output.split('\n'):
        if not line:
            continue

        # Shortstat output may not always exist (empty commits), but if it does, attatch it to the commit info.
        if line.startswith(' '):
            stat_tmp = [0, 0, 0]
            for item in line.strip().split(', '):
                count = int(item.split(' ', 1)[0])
                if 'deletion' in item:
                    stat_tmp[2] = count
                elif 'insert' in item:
                    stat_tmp[1] = count
                elif 'file' in item:
                    stat_tmp[0] = count
                else:
                    raise ValueError('Unhandled item "{}"'.format(item))

            commit_has_stat = True
            commit_lines[-1] = commit_lines[-1] + '|'.join(map(str, stat_tmp)) + ''
        else:
            if commit_lines and not commit_has_stat:
                commit_lines[-1] = commit_lines[-1] + '0|0|0'

            commit_has_stat = False
            commit_lines.append(line.strip())
   
    headings = ['date', 'name', 'email', 'sha', 'changed_files', 'insertions', 'deletions']
    commits = pd.read_csv(StringIO('\n'.join(commit_lines)), sep='|', parse_dates=[0],
                          infer_datetime_format=True, names=headings)
    commits.sort_values('date', inplace=True)
    commits['date'] = commits['date'].apply(lambda x: str(x))
    return {'commits': commits.to_dict(orient='records')}
    return (commits.to_json(orient='records', date_format='iso'))

    commits = []
    for commit_line in commit_lines:
        row = commit_line.split('|')
        date = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S %z')
        utc_date = date - date.utcoffset()
        utc_date = utc_date.replace(tzinfo=None)
        row[0]
        row[0] = utc_date

        commits.append(row)

    return commits


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
    results['first_commits'] = sorted(first_commits, key=lambda commit: commit['date'])

    return results


if __name__ == '__main__':
    repo = git.Repo('/Users/pelson/dev/iris')
    repo = git.Repo('/Users/pelson/dev/conda-forge/conda-forge-maint')
    from pprint import pprint
    pprint(commits(repo))
