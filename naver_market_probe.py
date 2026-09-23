"""Small, manual probe for public NAVER market endpoints; not production collection."""
import argparse, json, re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/html'}
PAGES = ['https://stock.naver.com/market/stock/kr', 'https://stock.naver.com/market/stock/kr/stocklist', 'https://stock.naver.com/market/stock/kr/industry/1', 'https://stock.naver.com/market/stock/kr/theme/1', 'https://stock.naver.com/market/stock/kr/trend/trader']

def candidates_from_html(text):
    return sorted(set(re.findall(r'https?://[^"\']*(?:api\.stock\.naver\.com|stock\.naver\.com)[^"\']+|/api/[^"\']+', text)))

def script_urls(html, base='https://stock.naver.com'):
    return sorted(set(re.findall(r'<script[^>]+src=["\']([^"\']+)', html)))

def absolute(url, base='https://stock.naver.com'):
    return url if url.startswith('http') else base + url if url.startswith('/') else base + '/' + url

def api_candidates(text):
    pattern=r'https://api\.stock\.naver\.com[^"\'` ]+|/api/[^"\'` ]+'
    return sorted(set(re.findall(pattern, text)))

def fetch_text(url):
    with urlopen(Request(url, headers=HEADERS), timeout=15) as response:
        return response.read().decode('utf-8','replace')

def discover():
    pages=[]; scripts=[]; seen=set(); candidates=[]
    for url in PAGES:
        try:
            html=fetch_text(url); srcs=[absolute(x) for x in script_urls(html)]
            pages.append({'url':url,'scripts':srcs,'htmlCandidates':candidates_from_html(html)})
            for src in srcs[:20]:
                if src in seen: continue
                seen.add(src)
                try:
                    body=fetch_text(src); found=api_candidates(body); scripts.append({'url':src,'candidates':found}); candidates.extend(found)
                except Exception as exc: scripts.append({'url':src,'error':str(exc)})
        except Exception as exc: pages.append({'url':url,'error':str(exc)})
    candidates=sorted(set(candidates)); results=[inspect(absolute(x, 'https://api.stock.naver.com') if x.startswith('/api/') else x) for x in candidates[:20]]
    out=ROOT/'probe_output'; out.mkdir(exist_ok=True)
    for name,value in [('scripts',scripts),('api_candidates',candidates),('discovery',{'pages':pages,'results':results})]: (out/f'{name}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'pages':len(pages),'scripts':len(scripts),'candidates':candidates,'results':results}

def trace(route):
    urls={'stocklist':'https://stock.naver.com/market/stock/kr/stocklist','trader':'https://stock.naver.com/market/stock/kr/trend/trader'}
    html={key:fetch_text(value) for key,value in urls.items()}
    chunks={key:set(absolute(x) for x in script_urls(value)) for key,value in html.items()}
    specific=chunks[route]-chunks['trader' if route=='stocklist' else 'stocklist']; common=chunks['stocklist']&chunks['trader']
    contexts=[]
    for url in list(specific)[:15]:
        try:
            body=fetch_text(url)
            for match in re.finditer(r'(?:fetch\(|axios|useQuery|queryFn|URLSearchParams)',body): contexts.append({'chunk':url,'context':body[max(0,match.start()-700):match.start()+1000]})
        except Exception: pass
    embedded={needle: needle in html[route] for needle in ('self.__next_f.push','__NEXT_DATA__','005930','000660','삼성전자','SK하이닉스')}
    result={'page':urls[route],'specificChunks':sorted(specific),'commonChunks':sorted(common),'fetchContexts':contexts[:20],'urlTemplates':sorted(set(x for c in contexts for x in api_candidates(c['context']))),'embeddedData':embedded,'validatedEndpoints':[]}
    out=ROOT/'probe_output';out.mkdir(exist_ok=True);(out/f'{route}_trace.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return result

def inspect(url):
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=15) as response:
            body=response.read().decode('utf-8','replace'); content=response.headers.get_content_type()
            try: payload=json.loads(body); is_json=True
            except json.JSONDecodeError: payload=None; is_json=False
            rows=payload if isinstance(payload,list) else payload.get('datas',[]) if isinstance(payload,dict) else []
            return {'url':url,'status':response.status,'contentType':content,'json':is_json,'rootKeys':list(payload) if isinstance(payload,dict) else [],'rowCount':len(rows) if isinstance(rows,list) else 0,'fields':list(rows[0]) if rows and isinstance(rows[0],dict) else [],'sample':rows[:3] if isinstance(rows,list) else [],'candidates':candidates_from_html(body) if not is_json else []}
    except Exception as exc: return {'url':url,'error':str(exc)}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('kind',nargs='?',default='list',choices=['list','discover','trace']); parser.add_argument('route',nargs='?',choices=['stocklist','trader']); args=parser.parse_args()
    if args.kind=='list': print('discover'); return
    print(json.dumps(trace(args.route) if args.kind=='trace' else discover(),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
