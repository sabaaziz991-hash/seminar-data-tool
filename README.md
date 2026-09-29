# כלי נתוני הסמינריון (SeminarDataTool)

כלי תוכנה לשחזור הניתוח של הסמינריון **"בולטות תקשורתית מוקדמת והתערבות ערעורית: ערעורי רצח והמתה בבית המשפט העליון
בישראל, 2010-2020"** (עזיז סאבא, החוג לקרימינולוגיה, המכללה האקדמית עמק יזרעאל).

**דף ההורדה:** https://sabaaziz991-hash.github.io/seminar-data-tool/

**הורדה ישירה:** [SeminarDataTool.zip](https://github.com/sabaaziz991-hash/seminar-data-tool/releases/latest/download/SeminarDataTool.zip)
(כ-108MB, ‏Windows 10 או 11, ‏64 סיביות)

## מה הכלי עושה
- **שחזור הניתוח:** מחשב מחדש את כל הלוחות של פרק הממצאים ומשווה אותם אוטומטית ל-342 הערכים שבעבודה (פלט SPSS 27).
- **צפייה בנתונים:** כל אחד מ-497 התיקים, כולל הפרסומים שנמצאו, תוצאת הערעור וטקסט פסק הדין.
- **ייצוא:** התוצאות ל-Excel, והנתונים עם קובצי פקודות ל-SPSS.
- **ייבוא מחדש:** הורדה חוזרת של נתוני בית המשפט מהמאגר הפתוח וחיפוש חוזר של הפרסומים לתיקים נבחרים.

אין צורך בהתקנה, ב-Python או ב-SPSS.

## הפעלה
1. להוריד את `SeminarDataTool.zip` ולחלץ את כל התוכן לתיקייה (לחצן ימני ← „חלץ הכל”).
2. ללחוץ פעמיים על `הפעלה.bat` או על `SeminarDataTool.exe`. הכלי נפתח בדפדפן.
3. אם Windows מציג את ההודעה „Windows protected your PC”, ללחוץ „More info” ואז „Run anyway”. ההודעה מופיעה כי התוכנה אינה חתומה דיגיטלית.

מדריך מלא: [docs/user-guide.pdf](docs/user-guide.pdf).

## על הנתונים
- **פסקי הדין:** מהמאגר הפתוח `LevMuchnik/SupremeCourtOfIsrael` ב-Hugging Face (Muchnik et al., 2023).
- **הפרסומים:** מחיפושי Google News לפי שם המערער, ומהמפתח לעיתונות של בית אריאלה (Primo).
- **כתבות לא שייכות:** כתבות שבבדיקה הידנית נמצאו כלא שייכות לתיק, בעיקר כתבות על אדם אחר בעל אותו שם, נשמרות בנתונים עם סיווגן כדי שהספירות יישארו מלאות. הכותרת והקישור שלהן אינם מוצגים.

## מבנה המאגר
| תיקייה | תוכן |
|---|---|
| `src/seminar_tool/` | קוד הכלי (Python) וממשק הדפדפן (`web/`) |
| `src/launcher/` | המפעיל `SeminarDataTool.exe` (C#) |
| `src/tests/` | בדיקות אוטומטיות, כולל השוואת 342 הערכים לעבודה |
| `src/build.py`, `src/SeminarDataTool.spec` | בניית החבילה (PyInstaller) |
| `data/` | נתוני המחקר שהכלי משתמש בהם |
| `docs/` | דף ההורדה והמדריך למשתמש |

## English summary
A portable Windows tool (Hebrew UI, runs in the browser) that reproduces every table of the findings chapter from the
study data and checks all 342 reported values against the paper. No installation, Python or SPSS is needed.
Download the ZIP from the [Releases](https://github.com/sabaaziz991-hash/seminar-data-tool/releases/latest) page,
extract it, and run `SeminarDataTool.exe`.
