"""Manual, headless browser network probe for public NAVER market pages."""
import argparse
import json
from pathlib import Path

PAGES = {'stocklist': 'https://stock.naver.com/market/stock/kr/stocklist',
         'trader': 'https://stock.naver.com/market/stock/kr/trend/trader'}
KEYWORDS = ('api.stock.naver.com', '/api/', 'stocklist', 'trader', 'investor',
            'foreign', 'institution', 'ranking', 'volume', 'trading', '_rsc=')

def relevant(url, content_type=''):
    return any(key in url.lower() for key in KEYWORDS) or 'json' in content_type or 'x-component' in content_type

def run_page(kind):
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        raise SystemExit('Playwright is not installed. Run: python3 -m pip install playwright && python3 -m playwright install chromium')
    records = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        def response(res):
            content_type = res.headers.get('content-type', '')
            if relevant(res.url, content_type):
                records.append({'method': res.request.method, 'url': res.url, 'resourceType': res.request.resource_type,
                                'status': res.status, 'contentType': content_type, 'hasPostData': bool(res.request.post_data)})
        page.on('response', response)
        page.goto(PAGES[kind], wait_until='networkidle', timeout=30000)
        browser.close()
    output = {'page': PAGES[kind], 'requests': records, 'dataRequests': records}
    path = Path(__file__).resolve().parent / 'probe_output'; path.mkdir(exist_ok=True)
    (path / f'browser_{kind}.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))

def inspect_page(kind):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True); page=browser.new_page(); page.goto(PAGES[kind],wait_until='networkidle',timeout=30000)
        data=page.evaluate("""() => {const v=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length), f=e=>({tag:e.tagName,role:e.getAttribute('role'),text:(e.innerText||e.value||'').trim().slice(0,200),ariaLabel:e.getAttribute('aria-label'),href:e.href||null,ariaSelected:e.getAttribute('aria-selected'),visible:v(e)}), keys=s=>Array.from({length:s.length},(_,i)=>s.key(i)).filter(Boolean);let c=[...document.querySelectorAll('button,a,[role=button],[role=tab],[role=radio],[role=option],[role=combobox],input,select,summary')].filter(v).map(f),k={};for(let x of ['005930','000660','삼성전자','SK하이닉스']){let e=[...document.querySelectorAll('body *')].find(e=>v(e)&&(e.innerText||'').includes(x));k[x]=e?{found:true,tag:e.tagName,text:e.innerText.slice(0,300)}:{found:false}}return {urlState:{url:location.href,pathname:location.pathname,search:location.search,hash:location.hash,title:document.title,historyLength:history.length},controls:c,knownStocks:k,storageKeys:{local:keys(localStorage),session:keys(sessionStorage)},rowCandidates:[...document.querySelectorAll('tr,li,[role=row]')].filter(v).slice(0,5).map(e=>e.innerText.slice(0,300)),resources:performance.getEntriesByType('resource').map(e=>({name:e.name,initiatorType:e.initiatorType,transferSize:e.transferSize}))}}""")
        browser.close()
    terms=('거래대금','거래량','52주','상승','하락','시가총액') if kind=='stocklist' else ('개인','외국인','기관','금융투자','보험','투신','연기금')
    data['targetControls']=[x for x in data['controls'] if any(t in x['text'] for t in terms)]
    path=Path(__file__).resolve().parent/'probe_output';path.mkdir(exist_ok=True);(path/f'inspect_{kind}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(data,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('stocklist','trader','all','inspect'));parser.add_argument('kind',nargs='?',choices=('stocklist','trader'));args=parser.parse_args()
    if args.command=='inspect': inspect_page(args.kind)
    else:
        for kind in PAGES if args.command=='all' else (args.command,): run_page(kind)
