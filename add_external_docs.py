"""
Adds table of contents of each external documentation to the
References menu
"""

import yaml
import json
import os
import sys
import re
import os.path as osp
from collections import OrderedDict, namedtuple
import fnmatch
import sh

def simple_glob(directory, glob_pattern):
    matches = []
    for root, dirnames, filenames in os.walk('src', followlinks=True):
        for filename in fnmatch.filter(filenames, glob_pattern):
            matches.append(osp.join(root, filename))
    return matches


def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    class OrderedLoader(Loader):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)


def ordered_dump(data, stream=None, Dumper=yaml.Dumper, **kwds):
    class OrderedDumper(Dumper):
        pass
    def _dict_representer(dumper, data):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            data.items())
    OrderedDumper.add_representer(OrderedDict, _dict_representer)
    return yaml.dump(data, stream, OrderedDumper, **kwds)


leadingHash = re.compile('#+\s+')

def read_toc(directory):
    def make_paths_absolute(tree):
        for t in tree:
            for k in t.keys():
                if isinstance(t[k], str):
                    t[k] = re.sub('^.', directory, t[k])
                else:
                    make_paths_absolute(t[k])
    toc_path = osp.join('src', directory, 'toc.yml')
    README_path = osp.join('src', directory, 'README.md')
    if osp.exists(toc_path):
        with open(toc_path) as f:
            toc = ordered_load(f)
    elif osp.exists(README_path):
        toc = ordered_load('- README: ./README.md')
    else:
        return None
    make_paths_absolute(toc)
    return toc


def find_entry(tree, name):
    return [p for p in tree if p.get(name)][0][name]


def walk_dict(d):
    it = None
    if isinstance(d, list):
        it = iter(d)
    elif isinstance(d, dict):
        it = d.values()
    if it:
        for item in it:
            for leaf in walk_dict(item):
                yield leaf
    else:
        yield d


def find_not_referenced(tocs):
    files = set([f.replace('src/', '') for f in simple_glob('src', '*.md')])
    referenced_files = set([r for toc in tocs for r in walk_dict(toc)])
    return list(files - referenced_files)


def get_name(filename):
    return '.'.join(osp.basename(filename).split('.')[:-1])


ExternalDoc = namedtuple('ExternalDoc', ['name', 'repository', 'doc_directory'])


def parse_external_doc_line(l):
    return ExternalDoc(*(l.strip().split(' ')))


has_pulled = {}
def fetch_external_doc(repository, destination):
    sh.rm('-rf', destination)
    sh.mkdir('-p', destination)
    with sh.pushd(destination):
        if osp.exists('.git') and not has_pulled.get(repository):
            sh.git('pull')
            has_pulled[repository] = True
        else:
            sh.git('clone', repository, '--depth', '1', '.')


def fetch_all_external_docs_from_file(filename):
    with open(filename) as f:
        external_docs = [parse_external_doc_line(l) for l in f]
    for name, repository, doc_directory in external_docs:
        tmpdir = osp.join('/tmp', name)
        print('Fetching %s...' % name)
        fetch_external_doc(repository, tmpdir)
        src_dir = osp.join('src', name)
        sh.rm('-f', src_dir)
        print('Linking %s...' % name)
        sh.ln('-s', osp.join(tmpdir, doc_directory), src_dir)


def main(argv):
    OUTSIDE_DOCS = 'OUTSIDE_DOCS'

    if '--fetch' in argv:
        fetch_all_external_docs_from_file(OUTSIDE_DOCS)

    with open('./mkdocs.yml') as f:
        data = ordered_load(f, yaml.SafeLoader)

    with open(OUTSIDE_DOCS) as f:
        outside_docs_conf = [l.strip().split(' ') for l in f.readlines()]
    outside_docs_conf = [
        {'name': c[0], 'repo': c[1], 'subdir': c[2]}
        for c in outside_docs_conf
    ]
    outside_doc_names = [c['name'] for c in outside_docs_conf]

    develop = find_entry(data['pages'], 'References')
    references = find_entry(develop, 'Stack and tools')

    del references[:]

    tocs = []
    for dir in outside_doc_names:
        abs = osp.join('./src', dir)
        toc = read_toc(dir)
        if toc:
            references.append({ dir: toc })
        tocs.append(toc)

    data['pages'].append({'hidden': [{get_name(k): k} for n, k in enumerate(sorted(find_not_referenced(tocs)))]})
    data['extra'] = {"outside_docs": outside_docs_conf}

    with open('mkdocs.yml', 'w+') as f:
        ordered_dump(data, f, indent=2, default_flow_style=False, Dumper=yaml.SafeDumper)

main(sys.argv)
