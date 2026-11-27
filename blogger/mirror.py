"""Mirror already delivered SL NEWS stories into its own Blogger site.
No publisher text or photos copied; reviewed original briefs or confirmed own FB posts only.
"""
import os, json, re, html, time, hashlib, unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from editorial import brief_for, official_video_for

HOME = "https://slnews247live.blogspot.com/"
PAGE = "1020689164470492"

def request(url, method="GET", data=None, token=None, form=False):
    headers = {"Accept":"application/json"}
    if token: headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        data = (urlencode(data) if form else json.dumps(data,ensure_ascii=False)).encode()
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method),timeout=30) as r:
            return json.load(r)
    except HTTPError as e:
        raise RuntimeError("Remote HTTP "+str(e.code)) from None

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFC",str(s)).casefold()
                   if unicodedata.category(c)[0] in "LMN")

def topic(article):
    source=article.get("source","").lower()
    for words, label in [(("sport",),"Sports"),(("business","economy"),"Business"),(("politic",),"Politics"),(("world","international"),"World")]:
        if any(w in source for w in words):return label
    title=norm(article["title_si"])
    rules={
        "Weather":("කාලගුණ","වැසි","වර්ෂා","කුණාටු","ගංවතුර","නායයෑ","සුළං"),
        "Sports":("ක්‍රීඩා","ක්‍රිකට්","පාපන්දු","ඔලිම්පික්","පදක්කම්"),
        "Business":("ව්‍යාපාර","ආර්ථික","මහ බැංකු","උද්ධමන","විනිමය","කොටස් වෙළඳ"),
        "Politics":("දේශපාලන","පාර්ලිමේන්තු","මැතිවරණ","ජනාධිපති","අගමැති","කැබිනට්"),
        "World":("විදේශීය","ජාත්‍යන්තර","ඇමරිකා","ඉන්දියා","චීන","රුසියා","යුක්‍රේන","ඊශ්‍රායල","ගාසා")}
    for k,words in rules.items():
        if any(norm(w) in title for w in words):return k
    return "Other"

def facebook_permalink(receipt):
    ident=str(receipt.get("id",""))
    fb=os.getenv("FB_PAGE_TOKEN","")
    if not fb or not re.fullmatch(PAGE+r"_\d+",ident):return ""
    try:
        result=request("https://graph.facebook.com/"+ident+"?fields=permalink_url",token=fb)
    except Exception:return ""
    u=result.get("permalink_url","")
    parsed=urlsplit(u)
    if parsed.scheme=="https" and parsed.hostname in ("www.facebook.com","facebook.com","m.facebook.com") and (PAGE in parsed.path or ident.split("_")[-1] in u):
        return u
    return ""

def main():
    names=("BLOGGER_CLIENT_ID","BLOGGER_CLIENT_SECRET","BLOGGER_REFRESH_TOKEN")
    if not all(os.getenv(n) for n in names):
        print("Blogger OAuth missing; nothing changed.");return
    if os.getenv("SLNEWS_BLOGGER_URL","").rstrip("/")!=HOME.rstrip("/"):
        print("Expected SL News site URL not configured; nothing changed.");return
    token=request("https://oauth2.googleapis.com/token","POST",{
        "client_id":os.environ[names[0]],"client_secret":os.environ[names[1]],
        "refresh_token":os.environ[names[2]],"grant_type":"refresh_token"},form=True)["access_token"]
    def api(path,params=None,method="GET",body=None):
        return request("https://www.googleapis.com/blogger/v3"+path+("?"+urlencode(params) if params else ""),method,body,token)
    blog=api("/blogs/byurl",{"url":HOME})
    if blog.get("url","").rstrip("/")!=HOME.rstrip("/") or "slnews" not in norm(blog.get("name","")):
        raise SystemExit("Wrong Blogger site; no writes.")
    path="/blogs/"+str(blog["id"])+"/posts"
    titles=set(); known=set(); page=None
    # Include drafts so uncertain prior writes are not repeated.
    while True:
        params={"view":"ADMIN","maxResults":100,"fetchBodies":"true"}
        if page:params["pageToken"]=page
        result=api(path,params)
        for p in result.get("items",[]):
            titles.add(norm(p.get("title","")))
            known.update(re.findall(r"slnews-story:([a-f0-9]{24})",p.get("content","")))
        page=result.get("nextPageToken")
        if not page:break
    state=json.loads(Path("data/sri_lanka_delivery.json").read_text())
    records=state.get("stories",{})
    candidates=sorted(records.values(),key=lambda r:r.get("article",{}).get("published",0))
    apply=os.getenv("SLNEWS_BLOGGER_PUBLISH_ENABLED","").lower()=="true"
    total=0
    for record in candidates:
        if total>=12:break
        a=record.get("article",{}); title=a.get("title_si",""); ident=str(a.get("id",""))
        if not title or not re.fullmatch("[a-f0-9]{24}",ident) or ident in known or norm(title) in titles:continue
        if not 0<=time.time()-a.get("published",0)<=7*86400:continue
        receipts=record.get("receipts",{})
        if not any(r.get("id") for r in receipts.values() if isinstance(r,dict)):continue
        brief=brief_for(a)
        fb=facebook_permalink(receipts.get("facebook",{}))
        if not brief and not fb:continue
        parts=["<!-- slnews-story:"+ident+" -->"]
        if brief:parts += ["<p>"+html.escape(p)+"</p>" for p in brief["body_si"].split("\n") if p.strip()]
        if fb:
            embed="https://www.facebook.com/plugins/post.php?"+urlencode({"href":fb,"show_text":"true","width":500})
            parts.append('<iframe title="SL NEWS 24/7 Facebook post" loading="lazy" src="'+html.escape(embed,quote=True)+'" width="500" height="650" style="max-width:100%;border:0" scrolling="yes" allowfullscreen="allowfullscreen"></iframe>')
            parts.append('<p><a href="'+html.escape(fb,quote=True)+'">Facebook පුවත බලන්න</a></p>')
        labels=[topic(a)]
        video=official_video_for(a)
        if video:
            from urllib.parse import parse_qs
            u=urlsplit(video)
            vid=(u.path.strip("/") if u.hostname=="youtu.be" else parse_qs(u.query).get("v",[""])[0])
            if re.fullmatch(r"[A-Za-z0-9_-]{11}",vid):
                parts.append('<iframe title="අදාළ නිල වීඩියෝව" loading="lazy" src="https://www.youtube-nocookie.com/embed/'+vid+'" width="560" height="315" allowfullscreen="allowfullscreen"></iframe>')
                labels.append("Videos")
        parts.append('<p><a href="https://t.me/slnews247">තවත් පුවත් සඳහා Telegram</a></p>')
        total+=1
        if not apply:continue
        result=api(path,{"isDraft":"false"},"POST",{"title":title,"content":"\n".join(parts),"labels":labels})
        if not result.get("id"):raise RuntimeError("Unconfirmed Blogger response; stop run")
        known.add(ident);titles.add(norm(title))
        state.setdefault("blogger_posts", {})[ident] = {
            "id": str(result["id"]), "url": result.get("url", ""), "at": time.time()}
        from fast_news import save
        save(state)
        print("Blogger accepted post",result["id"])
        try:
            from vidiq_tiktok_bridge import publish_tiktok
            outcome = publish_tiktok(state, [a], time.time(), save=save, max_items=1)
            print("TikTok same-run delivery:", json.dumps(outcome))
        except Exception as exc:
            print("TikTok same-run delivery needs review:", type(exc).__name__)
    print("Eligible new posts:",total,"mode:","publish" if apply else "preview")

if __name__=="__main__":main()
