from . import new_contributors as new_contrib
from . import all_commits
from . import last_commits
from . import commit_LOC_delta
from . import stargazers
from . import issues_opened_closed


# Format: "key", "Title", plot_module.
# The key must be a valid python variable name, and is also the prefix for the _prep and _viz functions in the module.
PLOTLY_PLOTS = (
    ['all_commits', 'All commits', all_commits],
    ['new_contributors', 'First commit date of new contributors', new_contrib],
    ['last_commits', 'Developer drop-off: days since last commit', last_commits],
    ['commit_LOC_delta', 'Lines of change per commit', commit_LOC_delta],
    ['stargazers', 'Repository stargazers', stargazers],
    ['issues', 'All time issues opened & closed', issues_opened_closed],
)
