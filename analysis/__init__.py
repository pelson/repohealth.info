import analysis.new_contributors as new_contrib
import analysis.all_commits as all_commits
import analysis.last_commits as last_commits
import analysis.commit_LOC_delta as commit_LOC_delta
import analysis.stargazers as stargazers
import analysis.issues_opened_closed as issues_open_closed


# Format: "key", "Title", plot_module.
# The key must be a valid python variable name, and is also the prefix for the _prep and _viz functions in the module.
PLOTLY_PLOTS = (
    ['all_commits', 'All commits', all_commits],
    ['new_contributors', 'First commit date of new contributors', new_contrib],
    ['last_commits', 'Developer drop-off: days since last commit', last_commits],
    ['commit_LOC_delta', 'Lines of change per commit', commit_LOC_delta],
    ['stargazers', 'Repository stargazers', stargazers],
    ['issues', 'All time issues opened & closed', issues_open_closed],
)
