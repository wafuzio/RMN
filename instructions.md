Sometimes, websites try to 'block' web scraping by authenticating your Session, IP Address, and User Agent (look these up if you don't know what they are), to make sure you don't scrape crazy amounts of data. However, these are usually either cookies or locally saved values. In this case, I have done the reverse engineering for you. If you make a request to amazon.com and look at the cookies, you'll see these three cookies: (others are irrelevent) https://imgur.com/a/hezTA8i

All three of these need to be provided to the search request you make. Since I am using python, it looks something like this:

initial = requests.get(url='https://amazon.com')
cookies = initial.cookies

search = requests.get(url='https://amazon.com/s?k=cereal', cookies=cookies)

This is a simple but classic example of how cookies can effect your web scraping expereince. Anti-Scraping mechanisms do get much more complex then this, usually hidden within heavily obfuscated javascript scripts, but in this case the company simply does not care. More for us!

After this, you should be able to get the raw HTML from the URL without an issue. Just don't get rate limited! Using proxies is not a solution as it will invalidate your session, so make sure to get a new session for each proxy.

After this, you can throw the HTML into an interpreter and find the values you need, like you do for every other site.