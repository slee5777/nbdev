# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/api/migrate.ipynb.

# %% auto 0
__all__ = ['MigrateProc', 'fp_md_fm', 'migrate_nb', 'migrate_md', 'nbdev_migrate']

# %% ../nbs/api/migrate.ipynb 2
from .process import *
from .frontmatter import *
from .frontmatter import _fm2dict, _re_fm_md, _dict2fm, _insertfm
from .processors import *
from .config import get_config, read_nb
from .sync import write_nb
from .showdoc import show_doc
from fastcore.all import *
import shutil

# %% ../nbs/api/migrate.ipynb 5
def _cat_slug(fmdict):
    "Get the partial slug from the category front matter."
    slug = '/'.join(fmdict.get('categories', ''))
    return '/' + slug if slug else '' 

# %% ../nbs/api/migrate.ipynb 7
def _file_slug(fname): 
    "Get the partial slug from the filename."
    p = Path(fname)
    dt = '/'+p.name[:10].replace('-', '/')+'/'
    return dt + p.stem[11:]    

# %% ../nbs/api/migrate.ipynb 9
def _replace_fm(d:dict, # dictionary you wish to conditionally change
                k:str,  # key to check 
                val:str,# value to check if d[k] == v
                repl_dict:dict #dictionary that will be used as a replacement 
               ):
    "replace key `k` in dict `d` if d[k] == val with `repl_dict`"
    if str(d.get(k, '')).lower().strip() == str(val.lower()).strip():
        d.pop(k)
        d = merge(d, repl_dict)
    return d

def _fp_fm(d):
    "create aliases for fastpages front matter to match Quarto front matter."
    d = _replace_fm(d, 'search_exclude', 'true', {'search':'false'})
    d = _replace_fm(d, 'hide', 'true', {'draft': 'true'})
    return d

# %% ../nbs/api/migrate.ipynb 10
def _fp_image(d):
    "Correct path of fastpages images to reference the local directory."
    prefix = 'images/copied_from_nb/'
    if d.get('image', '').startswith(prefix): d['image'] = d['image'].replace(prefix, '')
    return d

# %% ../nbs/api/migrate.ipynb 11
def _rm_quote(s): 
    title = re.search('''"(.*?)"''', s)
    return title.group(1) if title else s

def _is_jekyll_post(path): return bool(re.search(r'^\d{4}-\d{2}-\d{2}-', Path(path).name))

def _fp_convert(fm:dict, path:Path):
    "Make fastpages frontmatter Quarto complaint and add redirects."
    fs = _file_slug(path)
    if _is_jekyll_post(path):
        fm = compose(_fp_fm, _fp_image)(fm)
        if 'permalink' in fm: fm['aliases'] = [f"{fm['permalink'].strip()}"]
        else: fm['aliases'] = [f'{_cat_slug(fm) + fs}']
        if not fm.get('date'): 
            _,y,m,d,_ = fs.split('/')
            fm['date'] = f'{y}-{m}-{d}'
        
    if fm.get('summary') and not fm.get('description'): fm['description'] = fm['summary']
    if fm.get('tags') and not fm.get('categories'): 
        if isinstance(fm['tags'], str): fm['categories'] = fm['tags'].split()
        elif isinstance(fm['tags'], list): fm['categories'] = fm['tags']
    for k in ['title', 'description']:
        if k in fm: fm[k] = _rm_quote(fm[k])
    if fm.get('comments'): fm.pop('comments') #true by itself is not a valid value for comments https://quarto.org/docs/output-formats/html-basics.html#commenting, and the default is true
    return fm

# %% ../nbs/api/migrate.ipynb 14
class MigrateProc(Processor):
    "Migrate fastpages front matter in notebooks to a raw cell."
    def begin(self): 
        self.nb.frontmatter_ = _fp_convert(self.nb.frontmatter_, self.nb.path_)
        if getattr(first(self.nb.cells), 'cell_type', None) == 'raw': del self.nb.cells[0]
        _insertfm(self.nb, self.nb.frontmatter_)

# %% ../nbs/api/migrate.ipynb 21
def fp_md_fm(path):
    "Make fastpages front matter in markdown files quarto compliant."
    p = Path(path)
    md = p.read_text()
    fm = _fm2dict(md, nb=False)
    if fm:
        fm = _fp_convert(fm, path)
        return _re_fm_md.sub(_dict2fm(fm), md)
    else: return md 

# %% ../nbs/api/migrate.ipynb 30
_alias = merge({k:'code-fold: true' for k in ['collapse', 'collapse_input', 'collapse_hide']}, 
               {'collapse_show':'code-fold: show', 'hide_input': 'echo: false', 'hide': 'include: false', 'hide_output': 'output: false'})
def _subv1(s): return _alias.get(s, s)

# %% ../nbs/api/migrate.ipynb 31
def _re_v1():
    d = ['default_exp', 'export', 'exports', 'exporti', 'hide', 'hide_input', 'collapse_show', 'collapse',
         'collapse_hide', 'collapse_input', 'hide_output',  'default_cls_lvl']
    d += L(get_config().tst_flags).filter()
    d += [s.replace('_', '-') for s in d] # allow for hyphenated version of old directives
    _tmp = '|'.join(list(set(d)))
    return re.compile(f"^[ \f\v\t]*?(#)\s*({_tmp})(?!\S)", re.MULTILINE)

def _repl_directives(code_str): 
    def _fmt(x): return f"#| {_subv1(x[2].replace('-', '_').strip())}"
    return _re_v1().sub(_fmt, code_str)

# %% ../nbs/api/migrate.ipynb 33
def _repl_v1dir(cell):
    "Replace nbdev v1 with v2 directives."
    if cell.get('source') and cell.get('cell_type') == 'code':
        ss = cell['source'].splitlines()
        first_code = first_code_ln(ss, re_pattern=_re_v1())
        if not first_code: first_code = len(ss)
        if not ss: pass
        else: cell['source'] = '\n'.join([_repl_directives(c) for c in ss[:first_code]] + ss[first_code:])

# %% ../nbs/api/migrate.ipynb 38
_re_callout = re.compile(r'^>\s(Warning|Note|Important|Tip):(.*)', flags=re.MULTILINE)
def _co(x): return ":::{.callout-"+x[1].lower()+"}\n\n" + f"{x[2].strip()}\n\n" + ":::"
def _convert_callout(s): 
    "Convert nbdev v1 to v2 callouts."
    return _re_callout.sub(_co, s)

# %% ../nbs/api/migrate.ipynb 45
_re_video = re.compile(r'^>\syoutube:(.*)', flags=re.MULTILINE)
def _v(x): return "{{< " + f"video {x[1].strip()}" + " >}}"
def _convert_video(s):
    "Replace nbdev v1 with v2 video embeds."
    return _re_video.sub(_v, s)

# %% ../nbs/api/migrate.ipynb 49
_shortcuts = compose(_convert_video, _convert_callout)

def _repl_v1shortcuts(cell):
    "Replace nbdev v1 with v2 callouts."
    if cell.get('source') and cell.get('cell_type') == 'markdown':
        cell['source'] = _shortcuts(cell['source'])

# %% ../nbs/api/migrate.ipynb 50
def migrate_nb(path, overwrite=True):
    "Migrate Notebooks from nbdev v1 and fastpages."
    nbp = NBProcessor(path, procs=[FrontmatterProc, MigrateProc, _repl_v1shortcuts, _repl_v1dir], rm_directives=False)
    nbp.process()
    if overwrite: write_nb(nbp.nb, path)
    return nbp.nb

# %% ../nbs/api/migrate.ipynb 51
def migrate_md(path, overwrite=True):
    "Migrate Markdown Files from fastpages."
    txt = fp_md_fm(path)
    if overwrite: path.write_text(txt)
    return txt

# %% ../nbs/api/migrate.ipynb 52
@call_parse
def nbdev_migrate(
    path:str=None, # A path or glob containing notebooks and markdown files to migrate
    no_skip:bool=False, # Do not skip directories beginning with an underscore
):
    "Convert all markdown and notebook files in `path` from v1 to v2"
    _skip_re = None if no_skip else '^[_.]'
    if path is None: path = get_config().nbs_path
    for f in globtastic(path, file_re='(.ipynb$)|(.md$)', skip_folder_re=_skip_re, func=Path):
        try:
            if f.name.endswith('.ipynb'): migrate_nb(f)
            if f.name.endswith('.md'): migrate_md(f)
        except Exception as e: raise Exception(f'Error in migrating file: {f}') from e
