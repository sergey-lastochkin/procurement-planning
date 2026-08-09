// Illustrative configuration-mapped draft adapter, not a standalone module.
// НайтиЧерновикПоRecommendationID must be implemented against a target register.
Функция СоздатьЧерновикЗаказаПоставщику(RecommendationID, Данные) Экспорт
    Существующий = НайтиЧерновикПоRecommendationID(RecommendationID);
    Если ЗначениеЗаполнено(Существующий) Тогда Возврат Существующий; КонецЕсли;
    Документ = Документы.ЗаказПоставщику.СоздатьДокумент();
    Документ.Комментарий = "Recommendation " + RecommendationID;
    // Документ намеренно НЕ проводится автоматически.
    Документ.Записать();
    Возврат Документ.Ссылка;
КонецФункции
