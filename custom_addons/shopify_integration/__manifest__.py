{
    'name': 'Shopify Integration',
    'version': '1.0',				
    'depends': ['base', 'sale_management', 'stock', 'product'],			
    'data' : [					
	    'security/ir.model.access.csv',
        'data/scheduled_actions.xml',
        'views/shopify_config_views.xml',   
        'views/shopify_sync_log_views.xml',
        'views/manual_sync_wizard_views.xml',
        'views/menu.xml', 
    ],
    'installable': True,			
    'application': False,		
}