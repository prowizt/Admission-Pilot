SELECT [id],
         [학년도],
         [모집구분],
         [모집학과명],
         [정원내외구분명],
         [전형명],
         [모집인원],
         [created_at]
  FROM EXCEL_ADMISSIONQUOTA 
  WHERE [학년도] = N'2027' AND [전형명] IN (N'만학도', N'재외국민및외국인') 
  ORDER BY [모집학과명], [전형명], [모집구분]