# Facebook hashtags

The Facebook importer (`scripts/sync_facebook.py`) turns some hashtags in a
post into article `tags`, which the website uses to place news. Matching is
case-insensitive. All other hashtags stay in the article text and have no
effect. Setup and review guidance is in the [README](README.md).

## Hashtags that drive the site

| Hashtag | Tag | Effect |
| --- | --- | --- |
| `#u12`, `#u14`, `#u16`, `#u18` | `u12`, `u14`, `u16`, `u18` | Associates the post with that age group. A suffix is fine (`#U14Rugby`, `#U14s`, `#U16sRugby`, `#U18s`), but a following digit is not (`#u140`). |
| `#Community` | `community` | Shown in "Community news" on the Community page. |
| `#JoinUs` | `joinus` | Shown on the Join page. |
| `#Sponsor` | `sponsor` | Marks sponsor-related news. |
| `#news` | none | Default marker (`FACEBOOK_IMPORT_MARKER`) that selects a post for import unless `FACEBOOK_IMPORT_ALL` is `true`. |

A post can have several tags, e.g. `tags: ["community", "u14"]`.

## Hashtags seen in imported posts (no effect)

These appear in current news articles as plain text:
`#BucksLeague`, `#CountyRugby`, `#DRYBONES`, `#FosseFalcons`,
`#GirlsInSport`, `#GirlsPlayRugbyToo`, `#GirlsRugby`,
`#GirlsRugbyDevelopment`, `#GrassrootsRugby`, `#LeamingtonRFC`, `#RPGL`,
`#RugbyFamily`, `#RugbyTradition`, `#WarwickshireRugby`,
`#WomenAndGirlsRugby`, `#WomensRugby`.

Age-group hashtags seen: `#U14Rugby`, `#U14s`, `#U16Rugby`, `#U16sRugby`,
`#U18s`.
