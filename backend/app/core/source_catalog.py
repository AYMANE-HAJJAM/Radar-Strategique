"""Small, high-value source catalog. Environment JSON can replace each list."""
from app.modules.radar3_institutions.curated_sources import source_records
from app.modules.radar4_policies.curated_legal import source_records as legal_source_records

DEFAULT_SOURCES = {
    'RADAR_2_PROJECTS': (
        {'name': 'Morocco public news', 'index_url': 'https://www.maroc.ma/fr/actualites', 'parser_type': 'HTML_LIST', 'refresh_days': 2, 'priority': 10},
        {'name': 'Morocco public news page 2', 'index_url': 'https://www.maroc.ma/fr/actualites?page=1', 'parser_type': 'HTML_LIST', 'refresh_days': 2, 'priority': 11},
        {'name': 'Morocco public news page 3', 'index_url': 'https://www.maroc.ma/fr/actualites?page=2', 'parser_type': 'HTML_LIST', 'refresh_days': 2, 'priority': 12},
        {'name': 'Morocco public news page 4', 'index_url': 'https://www.maroc.ma/fr/actualites?page=3', 'parser_type': 'HTML_LIST', 'refresh_days': 2, 'priority': 13},
        {'name': 'Morocco public news page 5', 'index_url': 'https://www.maroc.ma/fr/actualites?page=4', 'parser_type': 'HTML_LIST', 'refresh_days': 2, 'priority': 14},
        {'name': 'Ministry of Culture news', 'index_url': 'https://mjcc.gov.ma/fr/actualites/', 'parser_type': 'HTML_LIST', 'refresh_days': 3, 'priority': 20},
        {'name': 'Al Omrane news', 'index_url': 'https://www.alomrane.gov.ma/Actualites', 'parser_type': 'HTML_LIST', 'refresh_days': 3, 'priority': 30},
        {'name': 'APDN project news', 'index_url': 'https://www.apdn.ma/', 'parser_type': 'HTML_LIST', 'refresh_days': 3, 'priority': 15},
    ),
    'RADAR_3_INSTITUTIONS': source_records() + (
        {'name': 'Composition officielle du gouvernement', 'index_url': 'https://www.maroc.ma/fr/le-maroc/gouvernement', 'parser_type': 'GOVERNMENT_ROLES', 'refresh_days': 7, 'priority': 1},
        {'name': 'Groupe Al Omrane', 'index_url': 'https://www.alomrane.gov.ma/Le-groupe/A-propos', 'parser_type': 'INSTITUTION_PROFILE', 'refresh_days': 21, 'priority': 5},
        {'name': 'Morocco appointments', 'index_url': 'https://www.maroc.ma/fr/actualites', 'parser_type': 'HTML_LIST', 'refresh_days': 7, 'priority': 10},
        {'name': 'Culture ministry news', 'index_url': 'https://mjcc.gov.ma/fr/actualites/', 'parser_type': 'HTML_LIST', 'refresh_days': 7, 'priority': 20},
    ),
    'RADAR_4_POLICIES': legal_source_records() + (
        {'name': 'Bulletin Officiel — édition française', 'index_url': 'https://www.sgg.gov.ma/DesktopModules/MVC/TableListBO/BO/AjaxMethod', 'parser_type': 'BO_PUBLICATIONS', 'refresh_days': 7, 'priority': 1},
        {'name': 'SGG', 'index_url': 'https://www.sgg.gov.ma/Legislation/ListeAvantProjets.aspx', 'parser_type': 'SGG_DRAFT_TABLE', 'refresh_days': 7, 'priority': 10},
        {'name': 'SGG consolidated laws', 'index_url': 'https://www.sgg.gov.ma/textesconsolides.aspx', 'parser_type': 'SGG_CONSOLIDATED', 'refresh_days': 14, 'priority': 8},
        {'name': 'Parliament legislation', 'index_url': 'https://www.chambredesrepresentants.ma/fr/legislation', 'parser_type': 'PARLIAMENT_STAGE', 'refresh_days': 7, 'priority': 20},
        {'name': 'CESE publications', 'index_url': 'https://www.cese.ma/fr/publications/', 'parser_type': 'HTML_LIST', 'refresh_days': 7, 'priority': 30},
        {'name': 'HCP publications', 'index_url': 'https://www.hcp.ma/Publications_r18.html', 'parser_type': 'HTML_LIST', 'refresh_days': 7, 'priority': 40},
    ),
    'RADAR_5_FUNDING': (
        {'name': 'World Bank Morocco projects API', 'index_url': 'https://search.worldbank.org/api/v2/projects?format=json&countrycode_exact=MA&rows=100', 'parser_type': 'JSON_API', 'refresh_days': 7, 'priority': 10},
        {'name': 'AfDB Morocco projects', 'index_url': 'https://www.afdb.org/en/countries/north-africa/morocco', 'parser_type': 'HTML_LIST', 'refresh_days': 7, 'priority': 20},
        {'name': 'EIB Morocco projects', 'index_url': 'https://www.eib.org/en/projects/loans/all/index.htm?q=&sortColumn=loanParts.loanPartStatus.statusDate&sortDir=desc&pageNumber=0&itemPerPage=25&pageable=true&country=MA', 'parser_type': 'HTML_LIST', 'refresh_days': 7, 'priority': 30},
        {'name': 'EBRD Morocco projects', 'index_url': 'https://www.ebrd.com/home/what-we-do/where-we-invest/morocco.html', 'parser_type': 'HTML_LIST', 'refresh_days': 7, 'priority': 40},
    ),
}
