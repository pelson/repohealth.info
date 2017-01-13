import analysis.new_contributors as new_contrib
import analysis.all_commits as all_commits
import analysis.commit_LOC_delta as commit_LOC_delta
import analysis.stargazers as stargazers


# Format: "key", "Title", plot_module.
# The key must be a valid python variable name, and is also the prefix for the _prep and _viz functions in the module.
PLOTLY_PLOTS = (
    ['all_commits', 'All commits', all_commits],
    ['new_contributors', 'First commit date of new contributors', new_contrib],
    ['commit_LOC_delta', 'Lines of change per commit', commit_LOC_delta],
    ['stargazers', 'Repository stargazers', stargazers],
)
