# Flink SQL Gateway

A simplified Flink SQL Gateway. Will be replaced by the real GW once upgraded for Flink 1.13
API is implemented according to https://docs.google.com/document/d/1DKpFdov1o_ObvrCmU-5xi-VrT6nR2gxq-BbswSSI9j8/edit#heading=h.cje99dt78an2

REST call implemented will be POST/v1/sessions/:session_id/statements

in case of success status line will be 200 "OK"

Return body will be `{"id": id}` containing the flink id
