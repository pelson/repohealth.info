import git
import github


def setup_parser(parser):
    parser.set_defaults(func=handle_args)
    parser.add_argument('token')
    parser.add_argument('repo_fullname', help='The full slug of the repo e.g. numpy/numpy')


def handle_args(args):
    main(args.token, args.repo_fullname)


def main(token, repo_slug):
    gh = github.Github(token)
    repo = gh.get_repo(repo_slug)
    print(repo)
    print(repo.forks)
    print(repo.open_issues_count)
    print(list(repo.get_stargazers()))
    print(list(repo.get_tags()))


if __name__ == '__main__':
    import argparse
    parser = parser = argparse.ArgumentParser()
    setup_parser(parser)
    args = parser.parse_args()
    args.func(args)
