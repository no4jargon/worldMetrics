insert into sources (code, name, homepage_url, notes)
values
  ('cea', 'Central Electricity Authority', 'https://cea.nic.in/', 'Power generation and PLF'),
  ('npp', 'National Power Portal', 'https://npp.gov.in/', 'Monthly generation reports actual'),
  ('dpiit_oea', 'Office of Economic Adviser / DPIIT', 'https://eaindustry.nic.in/', 'Eight core industries and cement'),
  ('vahan', 'VAHAN Dashboard', 'https://vahan.parivahan.gov.in/vahan4dashboard/', 'Vehicle registration counts used as auto sales proxy; retrieval workflow: /skill:vahan-dashboard'),
  ('mospi', 'Ministry of Statistics and Programme Implementation', 'https://mospi.gov.in/', 'CPI data and releases'),
  ('jll', 'JLL India', 'https://www.jll.co.in/', 'Residential market updates')
on conflict (code) do nothing;

with src as (
  select code, id from sources
), ds as (
  insert into datasets (source_id, code, name, frequency, unit_default, release_lag_days, acquisition_method, source_url)
  values
    ((select id from src where code = 'npp'), 'npp_monthly_generation', 'NPP Monthly Generation Reports Actual', 'monthly', 'BU', 20, 'playwright_xls_parse', 'https://npp.gov.in/monthlyGenerationReportsAct'),
    ((select id from src where code = 'dpiit_oea'), 'oea_core_industries', 'OEA Core Industries Cement', 'monthly', 'index', 30, 'pdf_parse', 'https://eaindustry.nic.in/'),
    ((select id from src where code = 'jll'), 'jll_residential_sales', 'JLL Residential Sales', 'quarterly', 'units', 20, 'html_scrape', 'https://www.jll.co.in/'),
    ((select id from src where code = 'vahan'), 'vahan_vehicle_registrations', 'VAHAN Vehicle Registrations', 'monthly', 'units', 7, 'agent_skill:vahan-dashboard', 'https://vahan.parivahan.gov.in/vahan4dashboard/'),
    ((select id from src where code = 'mospi'), 'mospi_cpi', 'MoSPI CPI', 'monthly', 'index', 12, 'html_scrape', 'https://mospi.gov.in/')
  on conflict (code) do nothing
  returning id, code
)
insert into metrics (dataset_id, code, name, category, description, unit, frequency, seasonal_adjustment, preferred_transform, is_derived)
values
  ((select id from datasets where code = 'npp_monthly_generation'), 'power_output_total', 'All-India electricity generation', 'power', 'Monthly all-India electricity generation from NPP All India actual report', 'BU', 'monthly', 'nsa', 'yoy', false),
  ((select id from datasets where code = 'npp_monthly_generation'), 'power_utilization_plf', 'All-India thermal PLF', 'power', 'Thermal power plant load factor from NPP All India actual report', 'percent', 'monthly', 'nsa', 'level', false),
  ((select id from datasets where code = 'oea_core_industries'), 'cement_output', 'Cement production', 'cement', 'Monthly cement output or index from core industries release', 'index', 'monthly', 'nsa', 'yoy', false),
  ((select id from datasets where code = 'oea_core_industries'), 'cement_utilization_est', 'Estimated cement capacity utilization', 'cement', 'Estimated monthly cement utilization using annual installed capacity denominator', 'percent', 'monthly', null, 'level', true),
  ((select id from datasets where code = 'jll_residential_sales'), 'home_sales_jll', 'Residential sales', 'housing', 'JLL top-7 cities residential sales', 'units', 'quarterly', null, 'qoq', false),
  ((select id from datasets where code = 'vahan_vehicle_registrations'), 'auto_sales_total', 'Domestic auto registrations', 'autos', 'Monthly domestic vehicle registration proxy from VAHAN; retrieve with /skill:vahan-dashboard', 'units', 'monthly', 'nsa', 'yoy', false),
  ((select id from datasets where code = 'vahan_vehicle_registrations'), 'two_wheeler_sales', 'Domestic two-wheeler registrations', 'autos', 'Monthly domestic two-wheeler registration proxy from VAHAN; retrieve with /skill:vahan-dashboard', 'units', 'monthly', 'nsa', 'yoy', false),
  ((select id from datasets where code = 'vahan_vehicle_registrations'), 'four_wheeler_sales', 'Domestic four-wheeler registrations', 'autos', 'Monthly domestic four-wheeler registration proxy from VAHAN; retrieve with /skill:vahan-dashboard', 'units', 'monthly', 'nsa', 'yoy', false),
  ((select id from datasets where code = 'mospi_cpi'), 'cpi_index', 'CPI index', 'inflation', 'Consumer Price Index base can change over time', 'index', 'monthly', null, 'level', false),
  ((select id from datasets where code = 'mospi_cpi'), 'cpi_headline', 'CPI headline inflation', 'inflation', 'Headline CPI inflation YoY', 'percent', 'monthly', null, 'yoy', false)
on conflict (code) do nothing;

insert into dashboard_panels (code, title, description, sort_order)
values
  ('overview', 'Overview', 'Top-level changes across the tracked economy', 1),
  ('power', 'Power', 'Output and utilization trends', 2),
  ('construction', 'Construction', 'Cement and housing activity', 3),
  ('demand', 'Demand', 'Autos and consumer-sensitive activity', 4),
  ('inflation', 'Inflation', 'Price levels and direction', 5),
  ('release_monitor', 'Release Monitor', 'Operational health of ingestors', 6)
on conflict (code) do nothing;
