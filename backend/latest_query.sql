SELECT TOP 30 [학년도],
         [모집학과명],
         [모집구분],
         [정원내외구분],
         [전형명],
         [모집인원]
  FROM [EXCEL_ADMISSIONQUOTA] 
  WHERE [학년도] = '2027' AND [모집학과명] LIKE '%치위생%' 
  ORDER BY [모집구분], [전형명]