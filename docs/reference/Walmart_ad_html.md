# Walmart Ad HTML – Reference

## Search URL
```
https://www.walmart.com/search?q={keyword}
```

## Ad Modules + Selectors

### Programmatic Banner (top/bottom)
**CSS:** `a.ad, a.adctr`

### Sponsored Brand (SBA)
**CSS:** `[data-testid="sba-container"]`

### Tile Takeover
**CSS:** `[data-testid="tile-take-over"]`

### Sponsored Brand Video (SBV)
**CSS:** `[data-testid="search-video-in-grid"]` (contains `<video>`)

## Redirect URLs
- `sp/track?…&rd=<encoded_url>` → decode "rd" param
- `dad/trk` (encrypted) → keep original URL

## Notes
- **⚠️ CAPTCHA WARNING:** Walmart uses PerimeterX bot protection
- You will likely need to solve CAPTCHA on EVERY run (this is normal)
- Persistent profile helps but doesn't eliminate CAPTCHA
- **Headed mode (browser visible) is REQUIRED** for manual CAPTCHA solving
- Store/location may influence creatives. For deterministic tests, seed store via profile

## Why CAPTCHA Persists
PerimeterX tracks:
- Browser fingerprints
- Behavioral patterns  
- Session continuity
- Network patterns

Even with a saved profile, each new browser session triggers CAPTCHA because:
1. New browser instance = new fingerprint
2. Automated behavior patterns are detected
3. No mouse movements/human interaction before search

**This is expected behavior - just solve the CAPTCHA each time.**

## Setup Instructions

### 1. Create Authenticated Profile
```bash
./scripts/setup_walmart_profile.sh
```

This will:
1. Open browser to walmart.com
2. Prompt you to solve CAPTCHA if it appears
3. Let you browse naturally to establish trust
4. Save the session for future runs

### 2. Set Environment Variable
```bash
export WALMART_PROFILE_DIR="$HOME/Documents/Amazon_Scrape/profiles/walmart"
```

### 3. Run Scraper
The scraper will use the saved session and should bypass CAPTCHA.

## CAPTCHA Behavior

**If CAPTCHA is detected:**
- **Headed mode (headless=False):** Browser stays open for 60 seconds, waiting for you to solve it
- **Headless mode:** Returns error immediately (cannot solve CAPTCHA without display)

**Solution:** Always use a persistent profile with pre-solved CAPTCHA

# Ad Cards

<div class="w_3jM4 pa0" id="SEARCH-DynamicAdContainer-zonebottom-acne skin care-"><section data-dca-id="M:B5CE2C8D14" data-dca-type="module"><div class="mr2-m ml4-l mr4-l" data-testid="galleryBottom"><div class="maxWidthSection cardsCarousel"><style>
    .maxWidthSection {
      margin: 0px auto 16px auto;
      display: grid;
    }
    .cardsCarousel {
      padding-left: 0;
    }
    @media (min-width: 320px) and (max-width: 769px) {
      .cards {
        max-width: 360px;
        margin: 0 auto;
      }
      .cardsCarousel {
        width: 100%;
      }
    }
    @media (min-width: 320px) and (max-width: 383px) {
      .cardsCarousel {
        padding-left: 12px;
      }
    }
    @media (min-width: 770px) {
      .cards {
        max-width: 752px;
      }
      .cardsCarousel {
        max-width: 87%;
      }
    }
    @media (min-width: 840px) {
      .cards {
        max-width: 752px;
      }
      .cardsCarousel {
        max-width: 808px;
      }
    }
    @media (min-width: 1199px) {
      .cards {
        max-width: 1024px;
      }
      .cardsCarousel {
        max-width: 1224px;
      }
    }</style><section class="ma bb b--near-white bn-l pb3 pb0-m"><h4 class="f3 ml1 ma0 mb2 dark-gray truncate lh-title">Brands you may like</h4><div class="flex flex-column justify-center relative" data-testid="horizontal-scroller-undefined" data-dca-id="7d661833-d81c-44e8-b168-e24fbc33ec61" data-dca-name="ui_horizontal_scroller:tempo_slot_context" data-dca-type="module"><a link-identifier="horizontalScrollerPrevious" class="absolute dn z-5 bg-white br-100 pa0 pointer hidden-child br-100 nav-control left-1" aria-label="Previous slide of list" aria-disabled="true" data-testid="horizontal-scroller-previous" data-dca-intent="swipeRight" data-dca-name="ItemCarouselPreviousButton" tabindex="0" role="button" data-dca-id="L:725BAF5955"><i class="ld ld-ChevronLeft" style="font-size: 1.5rem; vertical-align: -0.25em; padding: 12px; width: 1.5rem; height: 1.5rem; box-sizing: content-box;"></i></a><ul data-testid="carousel-container" class="list ma0 pl0 overflow-x-scroll hidesb hidesb-wk relative overflow-y-hidden justify-start carousel-peek-3-point-2 carousel-peek-3-point-5-xl" data-dca-id="M:D28DC31C98" data-dca-type="module" style="display: grid; grid-auto-flow: column; scroll-snap-type: x mandatory; max-height: fit-content;"><li class="flex flex-column flex items-start" data-slide="0" style="scroll-snap-align: start;"><div style="width: 100%;"><div tabindex="0"><div class="relative sponsorLabel "><iframe id="00-187cfb0011c2a15b25abbd5476124038-148347c3a0ea2762-00-2861671152044313-gallerybottom1" data-ad-type="gallerybottom1" data-ad-component-type="display" data-testid="gallerybottom1" class="w-100 v-mid bw0" height="309" name="" title="Walmart Advertisement" sandbox="allow-same-origin allow-scripts allow-top-navigation-by-user-activation allow-forms allow-popups" scrolling="no" src="https://i5.walmartimages.com/dfw/63fd9f59-d6ba/07b8ea82-184c-4ea3-8ac0-5dc1981e40c8/v33/safeframe.html" role="none"></iframe><style>
          .sponsorLabel {
              font-size: .75rem;
              width: 100%;
          }
          .searchAndBrowse {
              max-width: 1232px;
              margin: auto;
          }
          
          
          
          
          
          
          
          
            .galleryCarouselClasses {
                    margin-right: 0px;
                    padding-right: 0px;
                    max-width: 164px;
                }
            @media screen and (min-width: 300px) and (max-width: 719px) {
                .galleryCarouselClasses {
                        max-width: 164px;
                }
            }
            @media screen and (min-width: 720px) and (max-width: 1197px) {
                .galleryCarouselClasses {
                    max-width: 229px;
                }
            }
            @media screen and (min-width: 1198px) {
                .galleryCarouselClasses {
                    max-width: 307px;
                }
            }
        
          </style><div class="tr mt1 mt2-ns gray f7  galleryCarouselClasses" style="height: 16px; color: rgb(116, 118, 124);">Sponsored</div></div></div></div></li><li class="flex flex-column flex items-start" data-slide="1"><div style="width: 100%;"><div tabindex="0"><div class="relative sponsorLabel "><iframe id="00-187cfb0011c2a15b25abbd5476124038-148347c3a0ea2762-00-2861671152044313-gallerybottom2" data-ad-type="gallerybottom2" data-ad-component-type="display" data-testid="gallerybottom2" class="w-100 v-mid bw0" height="309" name="" title="Walmart Advertisement" sandbox="allow-same-origin allow-scripts allow-top-navigation-by-user-activation allow-forms allow-popups" scrolling="no" src="https://i5.walmartimages.com/dfw/63fd9f59-d6ba/07b8ea82-184c-4ea3-8ac0-5dc1981e40c8/v33/safeframe.html" role="none"></iframe><style>
          .sponsorLabel {
              font-size: .75rem;
              width: 100%;
          }
          .searchAndBrowse {
              max-width: 1232px;
              margin: auto;
          }
          
          
          
          
          
          
          
          
            .galleryCarouselClasses {
                    margin-right: 0px;
                    padding-right: 0px;
                    max-width: 164px;
                }
            @media screen and (min-width: 300px) and (max-width: 719px) {
                .galleryCarouselClasses {
                        max-width: 164px;
                }
            }
            @media screen and (min-width: 720px) and (max-width: 1197px) {
                .galleryCarouselClasses {
                    max-width: 229px;
                }
            }
            @media screen and (min-width: 1198px) {
                .galleryCarouselClasses {
                    max-width: 307px;
                }
            }
        
          </style><div class="tr mt1 mt2-ns gray f7  galleryCarouselClasses" style="height: 16px; color: rgb(116, 118, 124);">Sponsored</div></div></div></div></li><li class="flex flex-column flex items-start" data-slide="2"><div style="width: 100%;"><div tabindex="0"><div class="relative sponsorLabel "><iframe id="00-187cfb0011c2a15b25abbd5476124038-148347c3a0ea2762-00-2861671152044313-gallerybottom3" data-ad-type="gallerybottom3" data-ad-component-type="display" data-testid="gallerybottom3" class="w-100 v-mid bw0" height="309" name="" title="Walmart Advertisement" sandbox="allow-same-origin allow-scripts allow-top-navigation-by-user-activation allow-forms allow-popups" scrolling="no" src="https://i5.walmartimages.com/dfw/63fd9f59-d6ba/07b8ea82-184c-4ea3-8ac0-5dc1981e40c8/v33/safeframe.html" role="none"></iframe><style>
          .sponsorLabel {
              font-size: .75rem;
              width: 100%;
          }
          .searchAndBrowse {
              max-width: 1232px;
              margin: auto;
          }
          
          
          
          
          
          
          
          
            .galleryCarouselClasses {
                    margin-right: 0px;
                    padding-right: 0px;
                    max-width: 164px;
                }
            @media screen and (min-width: 300px) and (max-width: 719px) {
                .galleryCarouselClasses {
                        max-width: 164px;
                }
            }
            @media screen and (min-width: 720px) and (max-width: 1197px) {
                .galleryCarouselClasses {
                    max-width: 229px;
                }
            }
            @media screen and (min-width: 1198px) {
                .galleryCarouselClasses {
                    max-width: 307px;
                }
            }
        
          </style><div class="tr mt1 mt2-ns gray f7  galleryCarouselClasses" style="height: 16px; color: rgb(116, 118, 124);">Sponsored</div></div></div></div></li><li class="flex flex-column flex items-start" data-slide="3" style="scroll-snap-align: start;"><div style="width: 100%;"><div tabindex="0"><div class="relative sponsorLabel "><iframe id="00-187cfb0011c2a15b25abbd5476124038-148347c3a0ea2762-00-2861671152044313-gallerybottom4" data-ad-type="gallerybottom4" data-ad-component-type="display" data-testid="gallerybottom4" class="w-100 v-mid bw0" height="309" name="" title="Walmart Advertisement" sandbox="allow-same-origin allow-scripts allow-top-navigation-by-user-activation allow-forms allow-popups" scrolling="no" src="https://i5.walmartimages.com/dfw/63fd9f59-d6ba/07b8ea82-184c-4ea3-8ac0-5dc1981e40c8/v33/safeframe.html" role="none"></iframe><style>
          .sponsorLabel {
              font-size: .75rem;
              width: 100%;
          }
          .searchAndBrowse {
              max-width: 1232px;
              margin: auto;
          }
          
          
          
          
          
          
          
          
            .galleryCarouselClasses {
                    margin-right: 0px;
                    padding-right: 0px;
                    max-width: 164px;
                }
            @media screen and (min-width: 300px) and (max-width: 719px) {
                .galleryCarouselClasses {
                        max-width: 164px;
                }
            }
            @media screen and (min-width: 720px) and (max-width: 1197px) {
                .galleryCarouselClasses {
                    max-width: 229px;
                }
            }
            @media screen and (min-width: 1198px) {
                .galleryCarouselClasses {
                    max-width: 307px;
                }
            }
        
          </style><div class="tr mt1 mt2-ns gray f7  galleryCarouselClasses" style="height: 16px; color: rgb(116, 118, 124);">Sponsored</div></div></div></div></li><li class="flex flex-column flex items-start" data-slide="4"><div style="width: 100%;"><div tabindex="0"><div class="relative sponsorLabel "><iframe id="00-187cfb0011c2a15b25abbd5476124038-148347c3a0ea2762-00-2861671152044313-gallerybottom5" data-ad-type="gallerybottom5" data-ad-component-type="display" data-testid="gallerybottom5" class="w-100 v-mid bw0" height="217" name="" title="Walmart Advertisement" sandbox="allow-same-origin allow-scripts allow-top-navigation-by-user-activation allow-forms allow-popups" scrolling="no" src="https://i5.walmartimages.com/dfw/63fd9f59-d6ba/07b8ea82-184c-4ea3-8ac0-5dc1981e40c8/v33/safeframe.html" role="none"></iframe><style>
          .sponsorLabel {
              font-size: .75rem;
              width: 100%;
          }
          .searchAndBrowse {
              max-width: 1232px;
              margin: auto;
          }
          
          
          
          
          
          
          
          
            .galleryCarouselClasses {
                    margin-right: 0px;
                    padding-right: 0px;
                    max-width: 164px;
                }
            @media screen and (min-width: 300px) and (max-width: 719px) {
                .galleryCarouselClasses {
                        max-width: 164px;
                }
            }
            @media screen and (min-width: 720px) and (max-width: 1197px) {
                .galleryCarouselClasses {
                    max-width: 229px;
                }
            }
            @media screen and (min-width: 1198px) {
                .galleryCarouselClasses {
                    max-width: 307px;
                }
            }
        
          </style><div class="tr mt1 mt2-ns gray f7  galleryCarouselClasses" style="height: 16px; color: rgb(116, 118, 124);">Sponsored</div></div></div></div></li></ul><a link-identifier="horizontalScrollerNext" class="absolute dn z-5 bg-white br-100 pa0 pointer db-l br-100 nav-control right-1" aria-label="Next slide of list" aria-disabled="false" data-testid="horizontal-scroller-next" data-dca-intent="swipeLeft" data-dca-name="ItemCarouselNextButton" tabindex="0" role="button" data-dca-id="L:D255F19F56"><i class="ld ld-ChevronRight" style="font-size: 1.5rem; vertical-align: -0.25em; padding: 12px; width: 1.5rem; height: 1.5rem; box-sizing: content-box;"></i></a></div></section></div></div></section></div>