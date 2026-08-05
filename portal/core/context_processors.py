def sidebar_menu(request):

    return {
        "sidebar_menu": [
            {
                "title": "Dashboard",
                "url": "/",
                "icon": "dashboard",
                "active": request.path == "/",
            },

            {
                "title": "Accounts",
                "url": "/accounts/",
                "icon": "account_tree",
                "active": request.path.startswith("/accounts"),
            },

            {
                "title": "Inbox",
                "url": "/inbox/",
                "icon": "mail",
                "active": request.path.startswith("/inbox"),
            },

            {
                "title": "Notifications",
                "url": "/notifications/",
                "icon": "notifications",
                "active": request.path.startswith("/notifications"),
            },


            {
                "section": "Configuration",
            },


            {
                "title": "Audit Logs",
                "url": "/audit-logs/",
                "icon": "history",
                "active": request.path.startswith("/audit-logs"),
            },

            {
                "title": "Sync Dashboard",
                "url": "/sync/",
                "icon": "monitoring",
                "active": request.path == "/sync/",
            },

            {
                "title": "Sync Logs",
                "url": "/sync/logs/",
                "icon": "sync_alt",
                "active": request.path.startswith("/sync/logs"),
            },

            {
                "title": "Health & Queue",
                "url": "/sync/health/",
                "icon": "health_and_safety",
                "active": request.path.startswith("/sync/health"),
            },
        ]
    }