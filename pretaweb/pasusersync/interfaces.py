from zope.component import Interface



class IPASUserSync(Interface):
    """ Produces a list users which should be added or deleted or updated
    """

    def pass_diff():
        """  @return a tuple of adds, removes
        """

class IPASUserDisabler(Interface):
    """ Hookpoint for customising how to disable a user in your site """

    def disable_user(self, userid):
        """ disable or remove the user from the db after they disapear from the alternate PAS plugin """

class IPASUserAdder(Interface):
    """ Implement site specific actions to add a ldap user profile to your site """

    def add_user(self, userid, from_plugin=None):
        """ Take user information from one PASPlugin and setup your site to reflect that users existance """
        


