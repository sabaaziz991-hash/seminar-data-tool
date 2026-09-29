* Encoding: UTF-8.
* ====================================================================.
* סמינריון: בולטות תקשורתית מוקדמת והתערבות ערעורית בערעורי רצח והמתה.
* קובץ 1: ייבוא קובץ הנתונים הסופי, תוויות משתנים וערכים, ושמירה כקובץ SAV.
* ====================================================================.

FILE HANDLE root /NAME='{{SPSS_FOLDER}}'.

GET DATA
  /TYPE=TXT
  /FILE='root/study_dataset_final.csv'
  /ENCODING='UTF8'
  /DELCASE=LINE
  /DELIMITERS=","
  /QUALIFIER='"'
  /ARRANGEMENT=DELIMITED
  /FIRSTCASE=2
  /VARIABLES=
    case_id A40
    case_number A30
    decision_date A10
    year F4.0
    year_c F3.0
    merits_appeal F1.0
    non_merits_reason A150
    homicide_murder F1.0
    panel_size F2.0
    media_any F1.0
    media_count F3.0
    media_bucket F1.0
    media_log F8.4
    media_district_count F3.0
    media_appeal_any F1.0
    media_appeal_count F3.0
    media_primo_any F1.0
    media_combined_appeal_any F1.0
    intervention F1.0
    defendant_helped F1.0
    outcome_direction F2.0
    relief_type F1.0
    timeline_clean F1.0
    media_ref_any F1.0
    media_ref_count F3.0
    media_ref_coverage F1.0
    media_ref_pressure F1.0
    media_ref_reasoning F1.0
    words F6.0
    reasoning_method A40
    r_words F6.0
    r_sentence_len F8.3
    r_sentence_len_p90 F8.3
    r_word_len F8.3
    r_long_words_pct F8.3
    r_very_long_words_pct F8.3
    r_paren_per_1000 F8.3
    media_district_any F1.0
    words_log F8.4
    r_words_log F8.4
    attempt_only F1.0
    media_district_window F1.0.
CACHE.
EXECUTE.

VARIABLE LABELS
  case_id 'מזהה תיק'
  case_number 'מספר הליך'
  decision_date 'תאריך פסק הדין בערעור'
  year 'שנת ההכרעה'
  year_c 'שנת ההכרעה (ממורכזת ל-2015)'
  merits_appeal 'ערעור על הכרעת דין או גזר דין'
  non_merits_reason 'סיבת החרגה (הליך שאינו ערעור לגופו)'
  homicide_murder 'סוג העבירה'
  panel_size 'מספר שופטי ההרכב'
  media_any 'בולטות תקשורתית מוקדמת (חלון מרכזי)'
  media_count 'מספר ידיעות מוקדמות (חלון מרכזי)'
  media_bucket 'קבוצת מספר ידיעות'
  media_log 'לוג (1 + מספר ידיעות)'
  media_district_count 'ידיעות בשלב הכרעת המחוזי'
  media_appeal_any 'בולטות בשלב הערעור בלבד'
  media_appeal_count 'ידיעות בשלב הערעור בלבד'
  media_primo_any 'בולטות לפי מאגר העיתונות (Primo)'
  media_combined_appeal_any 'בולטות בשלב הערעור (Google News או Primo)'
  intervention 'התערבות בית המשפט העליון'
  defendant_helped 'הקלה עם הנאשם'
  outcome_direction 'כיוון התוצאה מבחינת הנאשם'
  relief_type 'סוג ההתערבות'
  timeline_clean 'ציר זמן ודאי (ללא סימון לבדיקה)'
  media_ref_any 'אזכור תקשורת בפסק הדין (מאומת)'
  media_ref_count 'מספר אזכורי תקשורת מאומתים'
  media_ref_coverage 'אזכור סיקור התיק או טענה להשפעת התקשורת'
  media_ref_pressure 'טענה להשפעת התקשורת על ההליך'
  media_ref_reasoning 'אזכור תקשורת בתוך פרק ההנמקה'
  words 'אורך פסק הדין (מילים)'
  reasoning_method 'שיטת חילוץ פרק ההנמקה'
  r_words 'אורך ההנמקה (מילים)'
  r_sentence_len 'אורך משפט ממוצע בהנמקה'
  r_sentence_len_p90 'אורך משפט באחוזון 90'
  r_word_len 'אורך מילה ממוצע (אותיות)'
  r_long_words_pct 'שיעור מילים ארוכות (7 אותיות ומעלה)'
  r_very_long_words_pct 'שיעור מילים ארוכות מאוד (9 אותיות ומעלה)'
  r_paren_per_1000 'צפיפות סוגריים (ל-1,000 מילים)'
  media_district_any 'בולטות בשלב הערכאה הדיונית'
  words_log 'לוג אורך פסק הדין'
  r_words_log 'לוג אורך ההנמקה'
  attempt_only 'ניסיון לרצח בלבד (ללא מוות)'
  media_district_window 'חושב חלון שלב הערכאה הדיונית'.

VALUE LABELS
  merits_appeal 1 'ערעור לגופו' 0 'הליך אחר'
  /homicide_murder 1 'רצח' 0 'המתה אחרת'
  /media_any media_appeal_any media_primo_any media_combined_appeal_any media_district_any 1 'עם בולטות' 0 'ללא בולטות'
  /media_bucket 0 'אין ידיעות' 1 'ידיעה אחת' 2 '2-4 ידיעות' 3 '5 ידיעות ומעלה'
  /intervention 1 'התערבות' 0 'ללא התערבות'
  /defendant_helped 1 'הקלה' 0 'ללא הקלה'
  /outcome_direction -1 'החמרה' 0 'ללא שינוי' 1 'הקלה'
  /relief_type 0 'ללא שינוי' 1 'הקלה בעונש' 2 'המרה לעבירה קלה' 3 'זיכוי' 4 'החזרה לערכאה' 5 'החמרה בעונש'
  /timeline_clean 1 'ודאי' 0 'מסומן לבדיקה'
  /media_ref_any media_ref_coverage media_ref_pressure media_ref_reasoning 1 'יש אזכור' 0 'אין אזכור'.

VARIABLE LEVEL media_any media_appeal_any media_primo_any media_combined_appeal_any media_district_any intervention
  defendant_helped homicide_murder merits_appeal timeline_clean media_ref_any media_ref_coverage media_ref_pressure media_ref_reasoning (NOMINAL)
  /media_bucket relief_type outcome_direction (ORDINAL)
  /year year_c media_count media_log words r_words r_sentence_len r_sentence_len_p90 r_word_len r_long_words_pct r_very_long_words_pct r_paren_per_1000 words_log r_words_log panel_size media_ref_count (SCALE).

* Reverse-coded copies so that CROSSTABS /RISK reports the odds ratio for "with salience" vs "without".
RECODE media_any media_appeal_any media_primo_any media_combined_appeal_any media_district_any (1=1) (0=2)
  INTO r_media r_media_appeal r_media_primo r_media_combined r_media_district.
RECODE intervention defendant_helped media_ref_any media_ref_coverage media_ref_reasoning (1=1) (0=2) INTO r_intervention r_helped r_ref r_ref_cov r_ref_reas.
VALUE LABELS r_media r_media_appeal r_media_primo r_media_combined r_media_district 1 'עם בולטות' 2 'ללא בולטות'
  /r_intervention 1 'התערבות' 2 'ללא התערבות' /r_helped 1 'הקלה' 2 'ללא הקלה' /r_ref r_ref_cov r_ref_reas 1 'יש אזכור' 2 'אין אזכור'.
VARIABLE LABELS r_media 'בולטות מוקדמת (קידוד הפוך לחישוב יחס סיכויים)' r_intervention 'התערבות (קידוד הפוך)'.
EXECUTE.

SAVE OUTFILE='root/study_dataset_final.sav' /COMPRESSED.
