import {REEL_EV, REEL_DUR} from './app/src/Reel';
import {STORY_EV, STORY_DUR} from './app/src/Story';
import {FILM_EV, FILM_DUR} from './app/src/Film';
import {TALK_EV, TALK_DUR, TALK_VOICE} from './app/src/Talk';
console.log(JSON.stringify({reel: {dur: REEL_DUR, ev: REEL_EV, fade: 0.6}, story: {dur: STORY_DUR, ev: STORY_EV, fade: 2.5}, talk: {dur: TALK_DUR, ev: TALK_EV, voice: TALK_VOICE, fade: 2.5}, film: {dur: FILM_DUR, ev: FILM_EV, fade: 3.5}}));
