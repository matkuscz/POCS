import os
import pymongo

import gzip
import json

from bson import json_util
from datetime import date
from datetime import datetime
from warnings import warn

from pocs.utils import current_time


class PanMongo(object):

    def __init__(self, host='localhost', port=27017, connect=False):
        """Connection to the running MongoDB instance

        This is a collection of parameters that are initialized when the unit
        starts and can be read and updated as the project is running. The server
        is a wrapper around a mongodb collection.

        Args:
            host (str, optional): hostname running MongoDB
            port (int, optional): port running MongoDb
            connect (bool, optional): Connect to mongo on create, defaults to True

        """
        # Get the mongo client
        self._client = pymongo.MongoClient(host, port, connect=connect)

        self.collections = [
            'config',
            'current',
            'environment',
            'mount',
            'observations',
            'state',
            'weather',
        ]

        # Setup static connections to the collections we want
        for collection in self.collections:
            # Add the collection as an attribute
            setattr(self, collection, getattr(self._client.panoptes, 'panoptes.{}'.format(collection)))

    def insert_current(self, collection, obj, include_collection=True):
        """Insert an object into both the `current` collection and the collection provided

        Args:
            collection (str): Name of valid collection within panoptes db
            obj (dict or str): Object to be inserted
            include_collection (bool): Whether to also update the collection,
                defaults to True

        Returns:
            str: Mongo object ID of record in `collection`
        """
        _id = None
        try:
            current_obj = {
                'type': collection,
                'data': obj,
                'date': current_time(datetime=True),
            }

            # Update `current` record
            self.current.replace_one({'type': collection}, current_obj, True)

            if include_collection:
                # Insert record into db
                col = getattr(self, collection)
                _id = col.insert_one(current_obj).inserted_id
        except AttributeError:
            warn("Collection does not exist in db: {}".format(collection))
        except Exception as e:
            warn("Problem inserting object into collection: {}".format(e))

        return _id

    def get_current(self, collection):
        """Returns the most current record for the given collection

        Args:
            collection (str): Name of the collection to get most current from
        """
        return self.current.find_one({'type': collection})

    def export(self,
               yesterday=True,
               start_date=None,
               end_date=None,
               collections=['all'],
               backup_dir=None,
               compress=True):  # pragma: no cover
        """Exports the mongodb to an external file

        Args:
            yesterday (bool, optional): Export only yesterday, defaults to True
            start_date (str, optional): Start date for export if `yesterday` is False,
                defaults to None, e.g. 2016-01-01
            end_date (None, optional): End date for export if `yesterday is False,
                defaults to None, e.g. 2016-01-31
            collections (list, optional): Which collections to include, defaults to all
            backup_dir (str, optional): Backup directory, defaults to /backups
            compress (bool, optional): Compress output file with gzip, defaults to True

        Returns:
            list: List of saved files
        """
        if backup_dir is None:
            backup_dir = '{}/backups/'.format(os.getenv('PANDIR', default='/var/panoptes/'))

        if not os.path.exists(backup_dir):
            warn("Creating backup dir")
            os.makedirs(backup_dir)

        if yesterday:
            start_dt = (current_time() - 1. * u.day).datetime
            start = datetime(start_dt.year, start_dt.month, start_dt.day, 0, 0, 0, 0)
            end = datetime(start_dt.year, start_dt.month, start_dt.day, 23, 59, 59, 0)
        else:
            assert start_date, warn("start-date required if not using yesterday")

            y, m, d = [int(x) for x in start_date.split('-')]
            start_dt = date(y, m, d)

            if end_date is None:
                end_dt = start_dt
            else:
                y, m, d = [int(x) for x in end_date.split('-')]
                end_dt = date(y, m, d)

            start = datetime.fromordinal(start_dt.toordinal())
            end = datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, 0)

        if 'all' in collections:
            collections = self.collections

        date_str = start.strftime('%Y-%m-%d')
        end_str = end.strftime('%Y-%m-%d')
        if end_str != date_str:
            date_str = '{}_to_{}'.format(date_str, end_str)

        out_files = list()

        console.color_print("Exporting collections: ", 'default', "\t{}".format(date_str.replace('_', ' ')), 'yellow')
        for collection in collections:
            if collection not in self.collections:
                next
            console.color_print("\t{}".format(collection))

            out_file = '{}{}_{}.json'.format(backup_dir, date_str.replace('-', ''), collection)

            col = getattr(self, collection)
            entries = [x for x in col.find({'date': {'$gt': start, '$lt': end}}).sort([('date', pymongo.ASCENDING)])]

            if len(entries):
                console.color_print("\t\t{} records exported".format(len(entries)), 'yellow')
                content = json.dumps(entries, default=json_util.default)
                write_type = 'w'

                if compress:
                    console.color_print("\t\tCompressing...", 'lightblue')
                    content = gzip.compress(bytes(content, 'utf8'))
                    out_file = out_file + '.gz'
                    write_type = 'wb'

                with open(out_file, write_type)as f:
                    console.color_print("\t\tWriting file: ", 'lightblue', out_file, 'yellow')
                    f.write(content)

                out_files.append(out_file)
            else:
                console.color_print("\t\tNo records found", 'yellow')

        console.color_print("Output file: {}".format(out_files))
        return out_files


if __name__ == '__main__':  # pragma: no cover
    from astropy.utils import console
    from astropy import units as u

    PanMongo().export()
