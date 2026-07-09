SELECT [모집학과명],
         [정원내외구분],
         [전형명],
         [모집인원]
  FROM [EXCEL_ADMISSIONQUOTA] 
  WHERE [학년도] = '2027' AND [모집구분] LIKE '%수시1차%'