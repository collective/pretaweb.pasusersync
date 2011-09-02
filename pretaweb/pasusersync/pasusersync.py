
import logging

from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.PluggableAuthService.interfaces.plugins import IUserAdderPlugin, IPropertiesPlugin
from Products.PlonePAS.sheet import MutablePropertySheet


class PASUserSync(BrowserView):

    def __init__ (self, *args, **kwargs):
        BrowserView.__init__ (self, *args, **kwargs)
        self.portal = getToolByName(self.context, "portal_url")  .getPortalObject()


    def __call__ (self):

        request = self.request
        portal = getToolByName(self.context, "portal_url")  .getPortalObject()
        listPlugins = portal.acl_users.plugins.listPlugins

        # Get paramitors and corrispondign objects

        from_pluginid = request.get ("from")
        to_pluginid = request.get("to")

        # Allowing for more specific definition of the to property manager and
        # user manager
        if to_pluginid is None:
            to_properties_pluginid = request.get("to_properties")
            to_manager_pluginid = request.get("to_manager")
        else:
            to_properties_pluginid = to_pluginid
            to_manager_pluginid = to_pluginid


        # Get plugin objects

        from_properties_plugin = None
        to_properties_plugin = None
        to_manager_plugin = None

        for pluginId, p in listPlugins(IPropertiesPlugin):
            if p.id == from_pluginid:
                from_properties_plugin = p
            elif pluginId == to_properties_pluginid:
                to_properties_plugin = p


        for pluginId, p in listPlugins(IUserAdderPlugin):
            if pluginId == to_manager_pluginid:
                to_manager_plugin = p
                break;


        # Check we have everything

        if not (to_manager_plugin and to_properties_plugin and from_properties_plugin):
            raise Exception ("Cound not find needed plugin")


        # Do Sync

        return self.sync (from_properties_plugin, to_manager_plugin, to_properties_plugin,)



    #
    # Syncing
    #

    def sync (self, from_properties, to_manager, to_properties):


        # Stats
        cadds = 0
        cremoves = 0
        cupdates = 0
        cnotupdates = 0

        doneUsers = set()
        for userInfo in self.portal.acl_users.searchUsers():

            # Do sync opertaions on a valid and not-done user
            uid = userInfo["id"]
            if uid not in doneUsers:
                doneUsers.add (uid)


                user = self.getUser(uid)
                if user is None:
                    logging.info ("could not sync id: %s", uid)
                else:
                    logging.info ("syncing id: %s", uid)

                    # if None is returned from the followign, that would mean
                    # the plugin does not manage that user
                    fprop = self.getPropertiesForUser (from_properties, user)
                    tprop = self.getPropertiesForUser (to_properties, user)


                    # Operation on the user - update, add, remove, noop.
                    # Operation is determined by which pluging returns valid
                    # property sheets. 
                    if fprop and tprop:
                        if self.sync_update (user, fprop, tprop):
                            logging.info ("updated id: %s", uid)
                            cupdates += 1
                        else:
                            logging.info ("id: %s is up to date", uid)
                            cnotupdates += 1

                    elif fprop and (tprop is None):
                        self.sync_add (uid, to_manager, fprop, to_properties)
                        logging.info ("added id: %s", uid)
                        cadds += 1

                    elif (fprop is None) and tprop:
                        self.sync_remove (uid, to_manager)
                        logging.info ("removed id: %s", uid)
                        cremoves += 1

                    else:
                        # noop - Do nothing
                        logging.info ("sync not required for id: %s", uid)
                        cnotupdates += 1


        return "adds=%s updates=%s removes=%s not_updated=%s" % (cadds, cupdates, cremoves, cnotupdates)




    #
    # Sync Opertions
    #


    def sync_update (self, user, fprop, tprop):
        updated = False

        if isinstance (tprop, MutablePropertySheet):

            tpropMap = tprop.propertyMap()
            tkeys = set([propInfo["id"] for propInfo in tpropMap])

            # iterate from properties
            fpropMap = fprop.propertyMap()
            for propInfo in fpropMap:
                key = propInfo["id"]
                if key in tkeys:
                    fvalue = fprop.getProperty(key)
                    tvalue = tprop.getProperty(key)
                    
                    # compare value, is diff then update
                    if fvalue != tvalue:
                        tprop.setProperty (user, key, fvalue)
                        updated = True

        return updated


    def sync_add (self, uid, to_manager, fprop, to_properties):
        password = getToolByName(self.portal, 'portal_registration').generatePassword ()

        # do the deed
        to_manager.doAddUser (uid, password)

        # roperties Update
        user = self.getUser(uid)
        tprop = self.getPropertiesForUser (to_properties, user)
        self.sync_update (user, fprop, tprop)




    def sync_remove (self, uid, to_manager):
        to_manager.doDeleteUser (uid)




    #
    # Helper functions to retreive users and their properties
    #


    def getUser (self, uid):
        try:
            user = self.portal.acl_users.getUser(uid)
        except:
            logging.error ("error in getting user")
            user = None
        return user
    

    def getPropertiesForUser (self, plugin, user):
        try:
            prop = plugin.getPropertiesForUser(user)
        except:
            prop = None

        if prop and prop.hasProperty("fullname"): 
            return prop
        else:
            import pdb; pdb.set_trace()
            return None
            




