# כלי נתוני הסמינריון (SeminarDataTool)

כלי תוכנה לשחזור שיטת איסוף הנתונים של הסמינריון **"בולטות תקשורתית מוקדמת והתערבות ערעורית: ערעורי רצח והמתה בבית המשפט העליון
בישראל, 2010-2020"** (עזיז סאבא, החוג לקרימינולוגיה, המכללה האקדמית עמק יזרעאל).

**דף ההורדה:** https://sabaaziz991-hash.github.io/seminar-data-tool/

**הורדה ישירה:** [SeminarDataTool.zip](https://sabaaziz991-hash.github.io/seminar-data-tool/SeminarDataTool.zip)
(כ-62MB, ‏Windows 10 או 11, ‏64 סיביות)

## מה הכלי עושה
- **הורדת הנתונים מהמקור:** הורדה ישירה של מאגר פסקי הדין הפתוח של בית המשפט העליון (Hugging Face).
- **בניית אוכלוסיית המחקר:** אותם סינונים של העבודה (ע"פ, פסק דין סופי בשנים 2010-2020, עבירות המתה, נאשם מערער, החרגת מערערים בשם חסוי), עם הספירה אחרי כל שלב והשוואה לעבודה.
- **חיפוש וסיווג ב-Google News:** אותן שאילתות לפי שם מדויק בשני חלונות הזמן, והסיווג האוטומטי של כל ידיעה בכללים של המחקר (כפילות, מונחים לא קשורים, מונחי הקשר משפטי).
- **מדדי הטקסט:** חישוב מחדש של אורך פסק הדין וההנמקה, רכיבי המורכבות הטקסטואלית, אזכורי התקשורת בשלב האוטומטי וסימון „ניסיון לרצח בלבד”, עם השוואה לנתוני המחקר.
- **צפייה וסינון:** טבלת כל 497 התיקים עם סינון, וכרטיס לכל תיק עם הפרסומים שנמצאו, תוצאת הערעור וטקסט פסק הדין.

אין צורך בהתקנה או ב-Python.

## הפעלה
1. להוריד את `SeminarDataTool.zip` ולחלץ את כל התוכן לתיקייה (לחצן ימני ← „חלץ הכל”).
2. להיכנס לתיקייה `SeminarDataTool` שחולצה, וללחוץ פעמיים על הקובץ „הפעלה” (או על `SeminarDataTool`). הכלי נפתח בדפדפן.
3. אם מופיע חלון כחול „Windows protected your PC”, ללחוץ „More info” ואז „Run anyway”. זה צפוי, כי התוכנה הורדה מהאינטרנט ואינה חתומה דיגיטלית.

מדריך מלא: [docs/user-guide.pdf](docs/user-guide.pdf).

## על הנתונים
- **פסקי הדין:** מהמאגר הפתוח `LevMuchnik/SupremeCourtOfIsrael` ב-Hugging Face (Muchnik et al., 2023).
- **הפרסומים:** מחיפושי Google News לפי שם המערער.
- **כתבות לא שייכות:** כתבות שבבדיקה הידנית נמצאו כלא שייכות לתיק, בעיקר כתבות על אדם אחר בעל אותו שם, נשמרות בנתונים עם סיווגן כדי שהספירות יישארו מלאות. הכותרת והקישור שלהן אינם מוצגים.

## מבנה המאגר
| תיקייה | תוכן |
|---|---|
| `src/seminar_tool/` | קוד הכלי (Python) וממשק הדפדפן (`web/`) |
| `src/launcher/` | המפעיל `SeminarDataTool.exe` (C#) |
| `src/tests/` | בדיקות אוטומטיות, כולל השוואת מדדי הטקסט לנתוני המחקר |
| `src/build.py`, `src/SeminarDataTool.spec` | בניית החבילה (PyInstaller) |
| `data/` | נתוני המחקר שהכלי משתמש בהם |
| `docs/` | דף ההורדה, קובץ התוכנה (`SeminarDataTool.zip`) והמדריך למשתמש |

## English summary
A portable Windows tool (Hebrew UI, runs in the browser) that replicates the automatic part of the study's data-collection
method: it downloads the open Supreme Court judgments dataset, rebuilds the study population with the same filters,
re-runs the exact-name Google News queries and classifies every item with the study's automatic rules, and recomputes
the text measures of the judgments; every step is compared with the study data. No installation or Python is needed.
Download the ZIP from the [download page](https://sabaaziz991-hash.github.io/seminar-data-tool/), extract it, and run
`SeminarDataTool.exe`.
