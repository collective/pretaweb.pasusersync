from zope.component import Interface



class ILDAPUserSync(Interface):
    """ Produces a list ldap users which should be added or deleted or updated
    """

    def diff_ldap():
        """  @return a tuple of adds, removes
        """

    def sync_ldap():
        """ Compare ldap user list to the PAS user list and call IUserDisabler and IUserAdder as needed
        """

class IUserDisabler(Interface):
    """ Hookpoint for customising how to disable a user in your site """

    def disable_user(userid, pluginid=None):
        """ disable or remove the user from the db after they disapear from ldap """

class IUserAdder(Interface):
    """ Implement site specific actions to add a ldap user profile to your site """

    def add_user(self, userid, pluginid=None):
        """ Take user information from one PASPlugin and setup your site to reflect that users existance """
        


