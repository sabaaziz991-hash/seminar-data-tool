* Encoding: UTF-8.
* ====================================================================.
* קובץ 2: כל הניתוחים הסטטיסטיים של העבודה (לפי סדר הופעתם בפרק הממצאים).
* מדגם מרכזי: 478 ערעורים לגופו (merits_appeal = 1). מדגם מלא (497) - בדיקת רגישות.
* ====================================================================.

FILE HANDLE root /NAME='{{SPSS_FOLDER}}'.
GET FILE='root/study_dataset_final.sav'.
DATASET NAME study WINDOW=FRONT.

OMS /SELECT ALL /DESTINATION FORMAT=SPV OUTFILE='root/output/seminar_spss_output.spv' /TAG='spv'.
OMS /SELECT TABLES /DESTINATION FORMAT=XLSX OUTFILE='root/output/seminar_spss_tables.xlsx' /TAG='xlsx'.
OMS /SELECT TABLES /DESTINATION FORMAT=OXML OUTFILE='root/output/seminar_spss_tables.xml' /TAG='oxml'.

COMPUTE main = (merits_appeal = 1).
COMPUTE f_timeline = (merits_appeal = 1 AND timeline_clean = 1).
COMPUTE f_covered = (merits_appeal = 1 AND media_any = 1).
COMPUTE f_pre137 = (merits_appeal = 1 AND decision_date < '2019-07-10').
COMPUTE f_death = (merits_appeal = 1 AND attempt_only = 0).
COMPUTE f_dwin = (merits_appeal = 1 AND media_district_window = 1).
FORMATS main f_timeline f_covered f_pre137 f_death f_dwin (F1.0).
EXECUTE.

* ---------------------------------------------------------------- A. תיאור המדגם.
ECHO 'A. Sample description (main sample N=478)'.
FILTER BY main.
FREQUENCIES VARIABLES=year homicide_murder panel_size media_any media_bucket intervention relief_type timeline_clean
  /ORDER=ANALYSIS.
DESCRIPTIVES VARIABLES=media_count media_district_count media_appeal_count /STATISTICS=MEAN STDDEV MIN MAX SUM.
CROSSTABS /TABLES=homicide_murder timeline_clean BY media_any /CELLS=COUNT COLUMN /STATISTICS=CHISQ.
CROSSTABS /TABLES=year BY media_any /CELLS=COUNT COLUMN /STATISTICS=CHISQ.
CROSSTABS /TABLES=relief_type BY media_any /CELLS=COUNT COLUMN.

* ---------------------------------------------------------------- B. בדיקת ההשערה.
ECHO 'B. Main hypothesis: salience x intervention'.
CROSSTABS /TABLES=r_media BY r_intervention
  /CELLS=COUNT ROW EXPECTED
  /STATISTICS=CHISQ PHI RISK.

* ---------------------------------------------------------------- C. רגרסיה לוגיסטית.
ECHO 'C. Logistic regression'.
LOGISTIC REGRESSION VARIABLES intervention
  /METHOD=ENTER media_any
  /PRINT=CI(95)
  /CRITERIA=PIN(.05) POUT(.10) ITERATE(20) CUT(.5).
LOGISTIC REGRESSION VARIABLES intervention
  /METHOD=ENTER media_any year_c homicide_murder
  /PRINT=CI(95)
  /CRITERIA=PIN(.05) POUT(.10) ITERATE(20) CUT(.5).

* ---------------------------------------------------------------- D. בדיקות חוסן.
ECHO 'D1. Alternative salience measures (main sample)'.
CROSSTABS /TABLES=r_media_appeal r_media_primo r_media_combined BY r_intervention
  /CELLS=COUNT ROW /STATISTICS=CHISQ PHI RISK.
ECHO 'D1b. Trial-court stage only, appeals with a trial-court window (n=427)'.
FILTER BY f_dwin.
CROSSTABS /TABLES=r_media_district BY r_intervention /CELLS=COUNT ROW /STATISTICS=CHISQ PHI RISK.
FILTER BY main.
ECHO 'D2. Defendant relief as outcome'.
CROSSTABS /TABLES=r_media BY r_helped /CELLS=COUNT ROW /STATISTICS=CHISQ PHI RISK.
ECHO 'D3. Stratified by offence type (Mantel-Haenszel)'.
CROSSTABS /TABLES=r_media BY r_intervention BY homicide_murder
  /CELLS=COUNT ROW /STATISTICS=CHISQ RISK CMH(1).
ECHO 'D4. Timeline-certain subsample'.
FILTER BY f_timeline.
CROSSTABS /TABLES=r_media BY r_intervention /CELLS=COUNT ROW /STATISTICS=CHISQ PHI RISK.
ECHO 'D4b. Decisions before Amendment 137 took effect (10.7.2019)'.
FILTER BY f_pre137.
CROSSTABS /TABLES=r_media BY r_intervention /CELLS=COUNT ROW /STATISTICS=CHISQ PHI RISK.
ECHO 'D4c. Excluding attempted-murder-only appeals'.
FILTER BY f_death.
CROSSTABS /TABLES=r_media BY r_intervention /CELLS=COUNT ROW /STATISTICS=CHISQ PHI RISK.
ECHO 'D5. Full corpus including non-merits proceedings (N=497)'.
FILTER OFF.
USE ALL.
CROSSTABS /TABLES=r_media BY r_intervention /CELLS=COUNT ROW /STATISTICS=CHISQ PHI RISK.
FILTER BY main.

* ---------------------------------------------------------------- E. עוצמת הבולטות (מינון).
ECHO 'E. Dose-response by number of items'.
CROSSTABS /TABLES=media_bucket BY intervention /CELLS=COUNT ROW /STATISTICS=CHISQ.
FILTER BY f_covered.
NONPAR CORR /VARIABLES=media_count intervention /PRINT=SPEARMAN TWOTAIL NOSIG /MISSING=PAIRWISE.
FILTER BY main.

* ---------------------------------------------------------------- F. ניתוח משלים: אזכורי תקשורת בפסק הדין.
ECHO 'F. Media references in the judgment'.
CROSSTABS /TABLES=r_media BY r_ref r_ref_reas r_ref_cov /CELLS=COUNT ROW EXPECTED /STATISTICS=CHISQ PHI RISK.
CROSSTABS /TABLES=media_ref_pressure BY media_any /CELLS=COUNT COLUMN /STATISTICS=CHISQ.

* ---------------------------------------------------------------- G. ניתוח משלים: מורכבות טקסטואלית של ההנמקה.
ECHO 'G. Textual complexity of the reasoning'.
FREQUENCIES VARIABLES=reasoning_method.
* G1. תקנון ששת רכיבי הקושי (ציוני z ביחס למדגם הניתוח).
DESCRIPTIVES VARIABLES=r_sentence_len r_sentence_len_p90 r_word_len r_long_words_pct r_very_long_words_pct r_paren_per_1000
  /SAVE /STATISTICS=MEAN STDDEV MIN MAX.
* G2. ניתוח רכיבים ראשיים: רכיב אחד, ציון משוקלל לכל פסק דין (שיטת רגרסיה).
FACTOR /VARIABLES Zr_sentence_len Zr_sentence_len_p90 Zr_word_len Zr_long_words_pct Zr_very_long_words_pct Zr_paren_per_1000
  /MISSING LISTWISE
  /PRINT INITIAL KMO EXTRACTION FSCORE
  /CRITERIA FACTORS(1) ITERATE(25)
  /EXTRACTION PC
  /ROTATION NOROTATE
  /SAVE REG(ALL complexity).
VARIABLE LABELS complexity1 'מדד מורכבות טקסטואלית (רכיב ראשי ראשון)'.
RELIABILITY /VARIABLES=Zr_sentence_len Zr_sentence_len_p90 Zr_word_len Zr_long_words_pct Zr_very_long_words_pct Zr_paren_per_1000
  /SCALE('complexity') ALL /MODEL=ALPHA.
* G3. השוואת קבוצות.
MEANS TABLES=complexity1 r_words words r_sentence_len r_sentence_len_p90 r_word_len r_long_words_pct r_very_long_words_pct r_paren_per_1000 BY media_any
  /CELLS=COUNT MEAN STDDEV MEDIAN.
T-TEST GROUPS=media_any(1 0) /VARIABLES=complexity1 /CRITERIA=CI(.95).
NPAR TESTS /M-W=complexity1 r_words words r_sentence_len r_sentence_len_p90 r_word_len r_long_words_pct r_very_long_words_pct r_paren_per_1000 BY media_any(0 1).
* G4. בקרה לאורך ההנמקה.
REGRESSION /STATISTICS COEFF CI(95) R ANOVA
  /DEPENDENT complexity1 /METHOD=ENTER media_any r_words_log.

FILTER OFF.
USE ALL.

* ---------------------------------------------------------------- H. עוצמה סטטיסטית (נוסחת מבחן z לשני שיעורים, h של כהן).
ECHO 'H. Statistical power (two-proportion z test, Cohen h)'.
DATA LIST FREE / p1 p0 n1 n0.
BEGIN DATA
0.29 0.227513 100 378
END DATA.
COMPUTE h = 2*ARSIN(SQRT(p1)) - 2*ARSIN(SQRT(p0)).
COMPUTE n_eff = n1*n0/(n1+n0).
COMPUTE z = ABS(h)*SQRT(n_eff).
COMPUTE power_2s = CDF.NORMAL(z - 1.959964, 0, 1) + CDF.NORMAL(-z - 1.959964, 0, 1).
COMPUTE power_1s = CDF.NORMAL(z - 1.644854, 0, 1).
COMPUTE h_mde80 = (1.959964 + 0.841621)/SQRT(n_eff).
COMPUTE p1_mde80 = SIN((h_mde80 + 2*ARSIN(SQRT(p0)))/2)**2.
COMPUTE n1_needed = ((1.959964 + 0.841621)/h)**2 * (1 + n1/n0).
* one-sided alpha = .05, as in the decision rule for the hypothesis.
COMPUTE h_mde80_1s = (1.644854 + 0.841621)/SQRT(n_eff).
COMPUTE p1_mde80_1s = SIN((h_mde80_1s + 2*ARSIN(SQRT(p0)))/2)**2.
COMPUTE n1_needed_1s = ((1.644854 + 0.841621)/h)**2 * (1 + n1/n0).
FORMATS p1 p0 h power_2s power_1s h_mde80 p1_mde80 h_mde80_1s p1_mde80_1s (F8.4) n1 n0 n_eff n1_needed n1_needed_1s (F8.1).
SUMMARIZE /TABLES=p1 p0 n1 n0 h power_2s power_1s h_mde80 p1_mde80 n1_needed h_mde80_1s p1_mde80_1s n1_needed_1s
  /FORMAT=LIST NOCASENUM TOTAL=NO /TITLE='Power analysis' /CELLS=NONE.

OMSEND.
